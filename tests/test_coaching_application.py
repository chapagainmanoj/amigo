"""Real Coach Tool/controller/API boundaries with fictional models and activated test users."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.models.function import FunctionModel

from src.agent import catalogue
from src.agent.registry import ModeRegistry
from src.agent.runtime import ModeRuntime
from src.api.coaching import router
from src.auth import get_authenticated_user_id
from src.bot.handlers import BotHandlers
from src.coaching import coaching_callback
from src.config import Settings
from src.memory.sessions import SessionManager
from src.mode_readiness import CoachReadiness
from tests.fakes import FakeChannel, FakeScheduler, FakeStore
from tests.test_mode_routing import MutableClock, Script
from tests.test_modes import _participant


@pytest.fixture(params=[False, True], ids=["commands", "threaded"])
async def coach_app(monkeypatch, request):
    clock = MutableClock()
    for module in (
        "src.memory.coaching",
        "src.memory.proactive",
        "src.memory.modes",
        "tests.fakes",
    ):
        monkeypatch.setattr(f"{module}.utc_now", clock.utc_now)
    monkeypatch.setattr("src.config.settings", Settings(_env_file=None))
    readiness = CoachReadiness(True, True, True)
    monkeypatch.setattr("src.mode_readiness.coach_readiness", readiness)
    live = replace(catalogue.COACH, status="live")
    monkeypatch.setattr(catalogue, "COACH", live)
    store, channel = FakeStore(), FakeChannel(threads=request.param, channel_id="fake")
    owner, other = await _participant(store, 48101), await _participant(store, 48102)
    monkeypatch.setattr(store, "get_activation_state", AsyncMock(return_value={"completed": True}))
    for user in (owner, other):
        await store.grant_mode(user["user_id"], "coach", "owner", "fictional application test")
        await store.set_coaching_consent(user["user_id"], "coaching-v1")
    runtime = ModeRuntime(ModeRegistry((catalogue.DAILY, live)))
    handlers = BotHandlers(channel, store, SessionManager(store, clock), FakeScheduler(), runtime)
    monkeypatch.setattr(handlers, "_is_allowed", AsyncMock(return_value=True))
    script = Script()
    state = SimpleNamespace(
        store=store,
        channel=channel,
        owner=owner,
        other=other,
        runtime=runtime,
        handlers=handlers,
        script=script,
        readiness=readiness,
        clock=clock,
        update=0,
        ref=None,
    )

    async def send(text):
        state.update += 1
        async with runtime.override(model=FunctionModel(script.respond)):
            await handlers.handle_message(
                48101, text, update_id=state.update, conversation=state.ref
            )
        if text == "/mode coach":
            state.ref = channel.sent[-1]["conversation"] if request.param else None

    async def callback(data, chat=48101):
        await handlers.handle_callback(chat, 1, data)

    async def draft():
        await send("/mode coach")
        script.tool(
            "draft_program",
            {
                "goal": "Take a fictional walk",
                "success_measure": "I choose three walks",
                "check_in_days": [1, 5],
                "check_in_time": "18:00",
            },
        )
        script.text("Review your chosen plan before approving.")
        await send("Draft my chosen walking plan.")
        row = await store.get_coaching_program(owner["user_id"])
        approval = next(
            item
            for item in reversed(channel.sent)
            if item["buttons"] and item["buttons"][0][0]["text"] == "Approve program"
        )
        return row, approval["buttons"][0][0]["callback_data"]

    state.send, state.callback, state.draft = send, callback, draft
    return state


async def test_real_draft_tool_only_exact_participant_callback_activates_once(coach_app):
    env = coach_app
    row, approval = await env.draft()
    assert row["state"] == "draft" and row["starts_at"] is None
    assert len(approval.encode()) <= 64
    calls = len(env.script.requests)
    await env.send("/program")
    assert len(env.script.requests) == calls
    assert "approval" in env.channel.last_text.lower()
    assert (await env.store.get_coaching_program(env.owner["user_id"]))["state"] == "draft"
    await env.callback(approval, chat=48102)
    assert (await env.store.get_coaching_program(env.owner["user_id"]))["state"] == "draft"
    await env.callback(approval)
    active = await env.store.get_coaching_program(env.owner["user_id"])
    assert active["state"] == "active" and active["version"] == 2
    await env.callback(approval)
    assert await env.store.get_coaching_program(env.owner["user_id"]) == active
    assert not env.store.tasks and not env.store.reminders
    assert await env.store.get_coaching_program(env.other["user_id"]) is None


@pytest.mark.parametrize("denial", ["kill", "withdrawal", "activation", "grant"])
async def test_old_approval_cannot_bypass_current_admission(coach_app, monkeypatch, denial):
    env = coach_app
    _, approval = await env.draft()
    if denial == "kill":
        env.readiness.enabled = False
    elif denial == "withdrawal":
        await env.store.set_coaching_consent(env.owner["user_id"], None)
    elif denial == "activation":
        monkeypatch.setattr(
            env.store, "get_activation_state", AsyncMock(return_value={"completed": False})
        )
    else:
        await env.store.revoke_mode_grant(
            env.owner["user_id"], "coach", "owner", "fictional revocation test"
        )
    await env.callback(approval)
    row = await env.store.get_coaching_program(env.owner["user_id"])
    assert row["state"] == "draft" and row["starts_at"] is None


@pytest.mark.parametrize("denial", ["kill", "withdrawal"])
async def test_pause_stop_remain_available_after_denial_but_resume_denied(coach_app, denial):
    env = coach_app
    _, approval = await env.draft()
    await env.callback(approval)
    row = await env.store.get_coaching_program(env.owner["user_id"])
    if denial == "kill":
        env.readiness.enabled = False
    else:
        await env.store.set_coaching_consent(env.owner["user_id"], None)
    await env.callback(coaching_callback("pause", row["program_id"], row["version"]))
    paused = await env.store.get_coaching_program(env.owner["user_id"])
    assert paused["state"] == "paused"
    await env.callback(coaching_callback("resume", paused["program_id"], paused["version"]))
    assert await env.store.get_coaching_program(env.owner["user_id"]) == paused
    await env.callback(coaching_callback("stop", paused["program_id"], paused["version"]))
    assert (await env.store.get_coaching_program(env.owner["user_id"], row["program_id"]))[
        "state"
    ] == "stopped"


async def test_revised_summary_old_token_rejected_and_existing_term_shown(coach_app):
    env = coach_app
    row, original = await env.draft()
    await env.callback(original)
    active = await env.store.get_coaching_program(env.owner["user_id"])
    await env.callback(coaching_callback("pause", active["program_id"], active["version"]))
    env.clock.now += timedelta(days=10)
    await env.send("/mode coach")
    env.script.tool(
        "revise_program",
        {
            "program_id": row["program_id"],
            "expected_version": 3,
            "goal": "Choose a shorter fictional walk",
            "success_measure": "My own new measure",
            "check_in_days": [2],
            "check_in_time": "17:00",
        },
    )
    env.script.text("Review the revised summary.")
    await env.send("Revise the goal to my new chosen plan.")
    revised = await env.store.get_coaching_program(env.owner["user_id"])
    assert revised["state"] == "draft" and revised["ends_at"] == active["ends_at"]
    message = next(item for item in reversed(env.channel.sent) if item["buttons"])
    assert "approval does not restart" in message["text"]
    assert active["ends_at"] in message["text"]
    assert "14 days from first approval" not in message["text"]
    await env.callback(original)
    assert await env.store.get_coaching_program(env.owner["user_id"]) == revised
    await env.callback(message["buttons"][0][0]["callback_data"])
    assert (await env.store.get_coaching_program(env.owner["user_id"]))["ends_at"] == active[
        "ends_at"
    ]


async def test_api_export_delete_are_owned_and_preserve_conversation_messages(coach_app):
    env = coach_app
    await env.draft()
    await env.store.draft_coaching_program(
        env.other["user_id"],
        "other",
        "other",
        goal="Other private goal",
        success_measure="Other measure",
        check_in_days=[1],
        check_in_time="18:00",
        timezone="UTC",
    )
    other_before = await env.store.export_coaching_data(env.other["user_id"])
    messages_before = list(env.store.messages)
    app = FastAPI()
    app.state.store = env.store
    app.include_router(router)
    app.dependency_overrides[get_authenticated_user_id] = lambda: env.owner["supabase_auth_id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/coaching/export", params={"user_id": env.other["user_id"]}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert {row["user_id"] for row in response.json()["programs"]} == {env.owner["user_id"]}
        assert "Other private goal" not in response.text
        rejected = await client.post(
            "/api/coaching/delete",
            json={
                "confirmation": "delete my coaching records",
                "user_id": env.other["user_id"],
            },
        )
        assert rejected.status_code == 422
        response = await client.post(
            "/api/coaching/delete", json={"confirmation": "delete my coaching records"}
        )
        assert response.status_code == 200
        assert "Messages and provider copies remain" in response.json()["scope"]
    assert await env.store.export_coaching_data(env.owner["user_id"]) == {
        "programs": [],
        "entries": [],
    }
    assert await env.store.export_coaching_data(env.other["user_id"]) == other_before
    assert env.store.messages == messages_before


async def test_unconsumed_old_summary_token_cannot_approve_revised_draft(coach_app):
    env = coach_app
    row, old_token = await env.draft()
    env.script.tool(
        "revise_program",
        {
            "program_id": row["program_id"],
            "expected_version": 1,
            "goal": "My revised fictional goal",
            "success_measure": "My revised measure",
            "check_in_days": [3],
            "check_in_time": "16:00",
        },
    )
    env.script.text("Review the new exact summary.")
    await env.send("Revise my draft before I approve.")
    revised = await env.store.get_coaching_program(env.owner["user_id"])
    assert revised["version"] == 2 and revised["state"] == "draft"
    new_summary = next(item for item in reversed(env.channel.sent) if item["buttons"])
    await env.callback(old_token)
    assert await env.store.get_coaching_program(env.owner["user_id"]) == revised
    await env.callback(new_summary["buttons"][0][0]["callback_data"])
    assert (await env.store.get_coaching_program(env.owner["user_id"]))["state"] == "active"


async def test_guard_denies_next_turn_before_transcript_or_model_and_no_daily_fallback(coach_app):
    env = coach_app
    await env.draft()
    messages = list(env.store.messages)
    requests = len(env.script.requests)
    env.readiness.enabled = False
    await env.send("Fictional sensitive input after the kill switch.")
    assert env.store.messages == messages
    assert len(env.script.requests) == requests
    assert "prerequisites" in env.channel.last_text
    assert not env.store.tasks and not env.store.reminders


async def test_pause_stop_controls_cannot_mutate_other_owner(coach_app):
    env = coach_app
    _, approval = await env.draft()
    await env.callback(approval)
    row = await env.store.get_coaching_program(env.owner["user_id"])
    for action in ("pause", "stop"):
        await env.callback(coaching_callback(action, row["program_id"], row["version"]), chat=48102)
        assert await env.store.get_coaching_program(env.owner["user_id"]) == row


def test_program_tools_require_uuid_identifiers():
    from src.evaluation.gate_a import tool_schema

    tools = tool_schema("coach")
    owned = [tool for tool in tools if "program_id" in tool["parameters"].get("properties", {})]
    assert owned
    for tool in owned:
        assert tool["parameters"]["properties"]["program_id"]["format"] == "uuid"
