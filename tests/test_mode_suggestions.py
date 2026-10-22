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
    target = await state.backing.get_active_session(uid, "coach")
    assert target["session_id"] == confirmed["opened_session_id"]
    assert await state.backing.get_session_messages(target["session_id"]) == []
    assert confirmed["control_session_id"] == newer["session_id"]
    assert await state.backing.get_active_mode(uid, newer["session_id"]) == "coach"


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


@pytest.mark.parametrize("pending", ["handoff", "coaching"])
async def test_pending_confirmation_created_after_offer_blocks_atomic_opening(state, pending):
    store, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    offer = await store.create_mode_suggestion(uid, sid, "coach")
    if pending == "handoff":
        result = await state.backing.create_handoff(
            uid, sid, "daily", "coach", "Fictional pending question", source_grant_required=False
        )
        assert result["status"] == "pending"
    else:
        result = await state.backing.draft_coaching_program(
            uid,
            "post-offer-draft",
            "post-offer-draft",
            goal="Fictional reading",
            success_measure="Three pages",
            check_in_days=[4],
            check_in_time="12:00",
            timezone="UTC",
        )
        await state.backing.issue_coaching_approval(uid, result["program"]["program_id"], 1)
    assert await store.resolve_mode_suggestion(uid, offer["offer_id"], True) is None
    assert (await store.get_mode_suggestion(uid, offer["offer_id"]))["state"] == "declined"
    assert not await state.backing.get_active_session(uid, "coach")
    assert (await state.backing.get_active_mode(uid, sid)) is None


async def test_confirm_opens_owned_fixed_mode_session_without_carried_text_and_fences_retry(
    state, monkeypatch
):
    store, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    offer = await store.create_mode_suggestion(uid, sid, "coach")
    result = await store.resolve_mode_suggestion(uid, offer["offer_id"], True)
    target = await state.backing.get_active_session(uid, "coach")
    assert target["session_id"] == result["opened_session_id"]
    assert target["mode_id"] == target["active_mode_id"] == "coach"
    assert await state.backing.get_active_mode(uid, sid) == "coach"
    assert await state.backing.get_session_messages(target["session_id"]) == []
    assert (await store.claim_mode_suggestion_opening(uid, offer["offer_id"])) == {"status": "busy"}
    assert not await store.complete_mode_suggestion_opening(
        state.other["user_id"], offer["offer_id"], result["opening_claim_token"]
    )
    monkeypatch.setattr(
        "src.memory.suggestions.utc_now", lambda: datetime.now() + timedelta(minutes=6)
    )
    receipt = await store.claim_mode_suggestion_opening(uid, offer["offer_id"])
    assert receipt["offer"]["opened_session_id"] == target["session_id"]
    token = receipt["offer"]["opening_claim_token"]
    assert token != result["opening_claim_token"]
    assert not await store.complete_mode_suggestion_opening(
        uid, offer["offer_id"], result["opening_claim_token"]
    )
    assert not await store.release_mode_suggestion_opening(
        uid, offer["offer_id"], result["opening_claim_token"]
    )
    assert await store.complete_mode_suggestion_opening(uid, offer["offer_id"], token)
    assert not await store.claim_mode_suggestion_opening(uid, offer["offer_id"])
    assert not await store.complete_mode_suggestion_opening(uid, offer["offer_id"], token)


async def test_confirm_failure_leaves_offer_pending_and_selector_unchanged(state, monkeypatch):
    store, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    offer = await store.create_mode_suggestion(uid, sid, "coach")
    local = await state.backing._suggestions()
    monkeypatch.setattr(
        local, "_target_session", AsyncMock(side_effect=RuntimeError("fictional precommit failure"))
    )
    with pytest.raises(RuntimeError):
        await store.resolve_mode_suggestion(uid, offer["offer_id"], True)
    assert (await store.get_mode_suggestion(uid, offer["offer_id"]))["state"] == "pending"
    assert await state.backing.get_active_mode(uid, sid) is None
    assert not await state.backing.get_active_session(uid, "coach")


@pytest.mark.parametrize("threads", [False, True])
async def test_failed_provider_opening_retries_same_receipt_without_a_model_turn(state, threads):
    store, user = state.backing, state.user
    coach = replace(DAILY, id="coach", name="Coach", entitlement="grant", context=())
    runtime = ModeRuntime(ModeRegistry((DAILY, coach)))
    runtime.execution_model_for = AsyncMock(side_effect=AssertionError("no model on opening"))
    channel = FakeChannel(threads=threads)
    modes = ModeController(store, channel, FakeScheduler(), SessionManager(store), runtime)
    controller = ModeSuggestionController(
        modes,
        readiness=SuggestionReadiness(True, True, True, True),
        turn_clearance=AsyncMock(return_value=True),
    )
    offer = await store.create_mode_suggestion(
        user["user_id"], state.session["session_id"], "coach"
    )
    original = modes.conversations.ensure
    calls = {"count": 0}

    async def ensure(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("PRIVATE_PROVIDER_ERROR")
        return await original(*args, **kwargs)

    modes.conversations.ensure = ensure
    await controller.handle_callback(user, 82001, f"suggest:yes:{offer['offer_id']}")
    pending = await store.get_mode_suggestion(user["user_id"], offer["offer_id"])
    assert pending["state"] == "confirmed" and pending["opening_claim_token"] is None
    assert pending["opening_completed_at"] is None
    assert "retry" in channel.sent[-1]["text"].lower() and "PRIVATE" not in channel.sent[-1]["text"]
    await controller.handle_callback(user, 82001, f"suggest:yes:{offer['offer_id']}")
    complete = await store.get_mode_suggestion(user["user_id"], offer["offer_id"])
    assert complete["opening_completed_at"] is not None
    assert complete["opened_session_id"] == pending["opened_session_id"]
    target = await store.get_active_session(user["user_id"], "coach")
    assert await store.get_session_messages(target["session_id"]) == []
    sent = len(channel.sent)
    await controller.handle_callback(user, 82001, f"suggest:yes:{offer['offer_id']}")
    assert len(channel.sent) == sent
    runtime.execution_model_for.assert_not_awaited()


async def test_retry_cannot_override_a_later_manual_mode_choice_or_revoked_grant(state):
    store, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    offer = await store.create_mode_suggestion(uid, sid, "coach")
    row = await store.resolve_mode_suggestion(uid, offer["offer_id"], True)
    assert await store.release_mode_suggestion_opening(
        uid, offer["offer_id"], row["opening_claim_token"]
    )
    await state.backing.set_active_mode(uid, sid, "daily")
    assert await store.claim_mode_suggestion_opening(uid, offer["offer_id"]) is None
    await state.backing.set_active_mode(uid, sid, "coach")
    await state.backing.revoke_mode_grant(uid, "coach", "owner", "fictional revoke")
    assert await store.claim_mode_suggestion_opening(uid, offer["offer_id"]) is None


async def test_retry_is_rejected_after_a_newer_daily_control_session_is_created(state):
    store, uid, sid = state.store, state.user["user_id"], state.session["session_id"]
    offer = await store.create_mode_suggestion(uid, sid, "coach")
    row = await store.resolve_mode_suggestion(uid, offer["offer_id"], True)
    assert await store.release_mode_suggestion_opening(
        uid, offer["offer_id"], row["opening_claim_token"]
    )
    newer = await state.backing.create_session(uid)
    assert newer["session_id"] != row["control_session_id"]
    assert await store.claim_mode_suggestion_opening(uid, offer["offer_id"]) is None
    assert await state.backing.get_active_mode(uid, newer["session_id"]) is None
