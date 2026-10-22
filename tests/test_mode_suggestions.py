"""Offers carry no content and cannot run a target Turn without participant confirmation."""

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agent.catalogue import DAILY
from src.agent.registry import ModeRegistry
from src.agent.runtime import ModeRuntime
from src.bot.modes import ModeController
from src.memory.memory_store import InMemoryStore
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.mode_suggestions import (
    ModeSuggestionController,
    SuggestionReadiness,
    explicit_job_target,
)
from src.tools.context import ToolContext
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


class RPCDatabase:
    def __init__(self, backing):
        self.backing = backing

    def rpc(self, name, params):
        async def execute():
            args = {key.removeprefix("p_"): value for key, value in params.items()}
            method = getattr(self.backing, name)
            return SimpleNamespace(data=await method(**args))

        return SimpleNamespace(execute=execute)


@pytest.fixture(params=["fake", "memory", "supabase"])
async def state(request):
    backing = FakeStore() if request.param != "memory" else InMemoryStore()
    user = await backing.create_user(82001)
    other = await backing.create_user(82002)
    session = await backing.create_session(user["user_id"])
    await backing.grant_mode(user["user_id"], "coach", "owner", "fictional test")
    await backing.set_mode_suggestion_preference(user["user_id"], True)
    store = backing
    if request.param == "supabase":
        store = MemoryStore()
        store.db = RPCDatabase(backing)
    return SimpleNamespace(store=store, backing=backing, user=user, other=other, session=session)


@pytest.mark.parametrize(
    "text,target",
    [
        ("Help me build a habit of fictional reading", "coach"),
        ("I want to reflect on a fictional event", "reflect"),
        ("Help me compare laundry options", "recommender"),
        ("I feel sad", None),
        ("I have ignored all reminders", None),
        ("", None),
        ("/mode coach", None),
        ("I want to hurt myself; help me build a habit", None),
        ("I want to build a habit and help me reflect on something", None),
    ],
)
async def test_authored_rule_suite(text, target):
    assert await explicit_job_target(text) == target


async def test_single_offer_per_session_and_owned_single_use(state):
    s, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    offers = await asyncio.gather(*[s.create_mode_suggestion(uid, sid, "coach") for _ in range(5)])
    offer = next(o for o in offers if o)
    assert len([o for o in offers if o]) == 1
    assert not await s.get_mode_suggestion(state.other["user_id"], offer["offer_id"])
    assert not await s.resolve_mode_suggestion(state.other["user_id"], offer["offer_id"], True)
    results = await asyncio.gather(
        *[s.resolve_mode_suggestion(uid, offer["offer_id"], True) for _ in range(5)]
    )
    assert len([o for o in results if o]) == 1
    assert not await s.create_mode_suggestion(uid, sid, "coach")
    assert not {"text", "carried_request", "response", "history"} & offer.keys()


async def test_persistent_stop_and_decline_suppress_session(state):
    s, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    offer = await s.create_mode_suggestion(uid, sid, "coach")
    await s.set_mode_suggestion_preference(uid, False)
    assert not await s.resolve_mode_suggestion(uid, offer["offer_id"], True)
    await s.set_mode_suggestion_preference(uid, True)
    assert not await s.create_mode_suggestion(uid, sid, "coach")
    new = await state.backing.create_session(uid)
    offered = await s.create_mode_suggestion(uid, new["session_id"], "coach")
    assert offered
    await s.resolve_mode_suggestion(uid, offered["offer_id"], False)
    assert not await s.create_mode_suggestion(uid, new["session_id"], "coach")


async def test_grant_revocation_and_closed_session_refuse(state):
    s, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    assert not await s.create_mode_suggestion(state.other["user_id"], sid, "coach")
    offer = await s.create_mode_suggestion(uid, sid, "coach")
    await state.backing.revoke_mode_grant(uid, "coach", "owner", "fictional revoke")
    assert not await s.resolve_mode_suggestion(uid, offer["offer_id"], True)
    await state.backing.grant_mode(uid, "coach", "owner", "fictional grant")
    new = await state.backing.create_session(uid)
    offer = await s.create_mode_suggestion(uid, new["session_id"], "coach")
    await state.backing.close_session(new["session_id"])
    assert not await s.resolve_mode_suggestion(uid, offer["offer_id"], True)


async def test_expired_offer_and_pending_handoff(state, monkeypatch):
    s, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    await state.backing.set_active_mode(uid, sid, "daily")
    handoff = await state.backing.create_handoff(
        uid, sid, "daily", "coach", "fictional request", source_grant_required=False
    )
    assert handoff["status"] == "pending"
    assert not await s.create_mode_suggestion(uid, sid, "coach")
    await state.backing.resolve_handoff(uid, sid, handoff["handoff"]["handoff_id"], False)
    offer = await s.create_mode_suggestion(uid, sid, "coach")
    monkeypatch.setattr(
        "src.memory.suggestions.utc_now", lambda: datetime.now() + timedelta(days=1)
    )
    assert not await s.resolve_mode_suggestion(uid, offer["offer_id"], True)


@pytest.mark.parametrize("threads", [False, True])
async def test_application_off_default_confirmation_opens_only(state, threads):
    user, store = state.user, state.backing
    coach = replace(DAILY, id="coach", name="Coach", entitlement="grant", context=())
    runtime = ModeRuntime(ModeRegistry((DAILY, coach)))
    channel = FakeChannel(threads=threads)
    modes = ModeController(store, channel, FakeScheduler(), SessionManager(store), runtime)
    controller = ModeSuggestionController(modes)
    context = ToolContext(
        store, FakeScheduler(), channel, user, state.session["session_id"], 82001, "UTC", "test"
    )
    assert not await controller.offer(context, "Help me build a habit", "One small step.")
    controller.readiness = SuggestionReadiness(True, True, True, True)
    controller.turn_clearance = AsyncMock(return_value=True)
    offer = await controller.offer(context, "Help me build a habit", "One small step.")
    assert offer
    assert not await store.get_active_session(user["user_id"], "coach")
    await controller.handle_callback(user, 82001, f"suggest:yes:{offer['offer_id']}")
    target_session = await store.get_active_session(user["user_id"], "coach")
    assert target_session
    assert await store.get_session_messages(target_session["session_id"]) == []
    assert not store._mode_state.handoffs


async def test_withdrawn_mode_cannot_open(state):
    store, user = state.backing, state.user
    coach = replace(DAILY, id="coach", name="Coach", entitlement="grant", context=())
    registry = ModeRegistry((DAILY, coach))
    modes = ModeController(
        store, FakeChannel(), FakeScheduler(), SessionManager(store), ModeRuntime(registry)
    )
    controller = ModeSuggestionController(
        modes,
        readiness=SuggestionReadiness(True, True, True, True),
        turn_clearance=AsyncMock(return_value=True),
    )
    context = ToolContext(
        store,
        FakeScheduler(),
        modes.channel,
        user,
        state.session["session_id"],
        82001,
        "UTC",
        "test",
    )
    offer = await controller.offer(context, "Help me build a habit", "One small step.")
    modes.runtime = ModeRuntime(ModeRegistry((DAILY, replace(coach, status="withdrawn"))))
    controller.runtime = modes.runtime
    await controller.handle_callback(user, 82001, f"suggest:yes:{offer['offer_id']}")
    assert not await store.get_active_session(user["user_id"], "coach")


async def test_older_owned_open_daily_session_remains_valid_when_another_is_open(state):
    s, uid = state.store, state.user["user_id"]
    older = state.session["session_id"]
    newer = await state.backing.create_session(uid)
    assert newer["session_id"] != older
    offer = await s.create_mode_suggestion(uid, older, "coach")
    assert offer and offer["source_session_id"] == older
    confirmed = await s.resolve_mode_suggestion(uid, offer["offer_id"], True)
    assert confirmed and confirmed["state"] == "confirmed"
    assert not await state.backing.get_active_session(uid, "coach")


async def test_pending_coach_approval_suppresses_offer_but_expired_approval_does_not(
    state, monkeypatch
):
    s, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    result = await state.backing.draft_coaching_program(
        uid,
        "pending-draft",
        "pending-draft",
        goal="Fictional reading",
        success_measure="Three fictional pages",
        check_in_days=[4],
        check_in_time="12:00",
        timezone="UTC",
    )
    await state.backing.issue_coaching_approval(uid, result["program"]["program_id"], 1)
    assert not await s.create_mode_suggestion(uid, sid, "coach")
    monkeypatch.setattr(
        "src.memory.suggestions.utc_now", lambda: datetime.now() + timedelta(days=1)
    )
    assert await s.create_mode_suggestion(uid, sid, "coach")


async def test_null_or_nonboolean_confirmation_cannot_consume_or_confirm_offer(state):
    s, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    offer = await s.create_mode_suggestion(uid, sid, "coach")
    assert not await s.resolve_mode_suggestion(uid, offer["offer_id"], None)
    assert not await s.resolve_mode_suggestion(uid, offer["offer_id"], "false")
    assert (await s.get_mode_suggestion(uid, offer["offer_id"]))["state"] == "pending"
    assert (await s.resolve_mode_suggestion(uid, offer["offer_id"], False))["state"] == "declined"


@pytest.mark.parametrize("flag", [None, "false", 0, 1])
async def test_grant_requirement_requires_boolean_in_every_store_adapter(state, flag):
    with pytest.raises(ValueError, match="Boolean"):
        await state.store.create_mode_suggestion(
            state.user["user_id"], state.session["session_id"], "coach", grant_required=flag
        )
    assert not await state.store.get_mode_suggestion(
        state.user["user_id"], "00000000-0000-0000-0000-000000021111"
    )


async def test_release_readiness_alone_cannot_bypass_default_deny_turn_clearance(state):
    store, user = state.backing, state.user
    coach = replace(DAILY, id="coach", name="Coach", entitlement="grant", context=())
    channel = FakeChannel()
    modes = ModeController(
        store,
        channel,
        FakeScheduler(),
        SessionManager(store),
        ModeRuntime(ModeRegistry((DAILY, coach))),
    )
    controller = ModeSuggestionController(
        modes,
        readiness=SuggestionReadiness(True, True, True, True),
    )
    context = ToolContext(
        store, FakeScheduler(), channel, user, state.session["session_id"], 82001, "UTC", "denied"
    )
    assert not await controller.offer(context, "Help me build a habit", "Current response.")
    assert not channel.sent
    assert not (await store._suggestions()).offers


async def test_participant_preference_defaults_off_and_requires_explicit_opt_in(state):
    s, actor = state.store, state.other["user_id"]
    assert await s.get_mode_suggestion_preference(actor) is False
    session = await state.backing.create_session(actor)
    assert (
        await s.create_mode_suggestion(actor, session["session_id"], "coach", grant_required=False)
        is None
    )
    assert await s.set_mode_suggestion_preference(actor, True) is True
    assert await s.create_mode_suggestion(
        actor, session["session_id"], "coach", grant_required=False
    )
    assert await s.set_mode_suggestion_preference(actor, False) is False
    assert await s.get_mode_suggestion_preference(actor) is False
