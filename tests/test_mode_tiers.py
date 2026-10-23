"""Tiered Mode entitlements: Daily and Coach for everyone, the rest for full access."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from src.access import entitled, grant_required
from src.agent.catalogue import build_registry
from src.agent.registry import ModeRegistry
from src.agent.runtime import ModeRuntime
from src.bot.handlers import BotHandlers
from src.config import settings
from src.memory.sessions import SessionManager
from src.mode_readiness import (
    COACH_CONSENT_VERSION,
    COACH_PROCESSING_NOTICE,
    coach_entry_guard,
    reflect_entry_guard,
)
from tests.fakes import FakeChannel, FakeScheduler, FakeStore

FULL, TRIAL = 111, 222


@pytest.fixture(autouse=True)
def _tiers(monkeypatch):
    monkeypatch.setattr(settings, "allowed_telegram_chat_ids", str(FULL))
    monkeypatch.setattr(settings, "coach_trial_enabled", False)


async def _activated(store, chat_id):
    user = await store.create_user(chat_id)
    await store.update_user(
        user["user_id"],
        {"timezone": "UTC", "onboarding_complete": True, "supabase_auth_id": f"auth-{chat_id}"},
    )
    return await store.get_user_by_chat_id(chat_id)


@pytest.mark.parametrize(
    ("chat_id", "expected"),
    [
        (FULL, {"daily", "coach", "reflect", "recommender"}),
        (TRIAL, {"daily", "coach"}),
    ],
)
async def test_entitlement_matrix(chat_id, expected):
    store = FakeStore()
    user = await _activated(store, chat_id)
    allowed = {mode.id for mode in build_registry() if await entitled(store, user, mode)}
    assert allowed == expected


async def test_operator_grant_still_opens_full_access_modes_for_trial_users():
    store = FakeStore()
    user = await _activated(store, TRIAL)
    reflect = build_registry()["reflect"]
    assert grant_required(user, reflect)
    await store.grant_mode(user["user_id"], "reflect", "owner", "fictional test")
    assert await entitled(store, user, reflect)


async def test_full_access_bypasses_entry_guards():
    store = FakeStore()
    user = await _activated(store, FULL)
    context = SimpleNamespace(store=store, user=user)
    assert await coach_entry_guard(context) is None
    assert await reflect_entry_guard(context) is None


async def test_trial_coach_stays_closed_until_owner_attests_readiness(monkeypatch):
    store = FakeStore()
    context = SimpleNamespace(store=store, user=await _activated(store, TRIAL))
    assert "unavailable" in await coach_entry_guard(context)
    monkeypatch.setattr(settings, "coach_trial_enabled", True)
    assert await coach_entry_guard(context) == COACH_PROCESSING_NOTICE
    assert await reflect_entry_guard(context)


def _live_runtime():
    return ModeRuntime(ModeRegistry(replace(mode, status="live") for mode in build_registry()))


async def _send(handlers, store, chat_id, text):
    with patch.object(store, "get_activation_state", return_value={"completed": True}):
        await handlers.handle_message(chat_id, text)


async def test_trial_coach_consent_button_records_consent_and_admits(monkeypatch):
    monkeypatch.setattr(settings, "coach_trial_enabled", True)
    monkeypatch.setattr(settings, "access_mode", "registered")
    store, channel = FakeStore(), FakeChannel()
    runtime = _live_runtime()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler(), runtime)
    user = await _activated(store, TRIAL)

    await _send(handlers, store, TRIAL, "/mode coach")
    assert channel.last_text == COACH_PROCESSING_NOTICE
    button = channel.sent[-1]["buttons"][0][0]
    assert button["callback_data"] == f"consent:{COACH_CONSENT_VERSION}"

    with patch.object(store, "get_activation_state", return_value={"completed": True}):
        await handlers.handle_callback(TRIAL, 1, button["callback_data"])
    consent = await store.get_proactive_consent(user["user_id"], COACH_CONSENT_VERSION)
    assert consent and consent["policy_version"] == COACH_CONSENT_VERSION

    async def reply(messages, info):
        return ModelResponse(parts=[TextPart("Fictional coach reply")])

    async with runtime.override(model=FunctionModel(reply)):
        await _send(handlers, store, TRIAL, "/mode coach")
        await _send(handlers, store, TRIAL, "I want to walk more")
    assert channel.last_text == "Fictional coach reply"


async def test_consent_callback_refused_while_coach_readiness_closed(monkeypatch):
    monkeypatch.setattr(settings, "access_mode", "registered")
    store, channel = FakeStore(), FakeChannel()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler())
    user = await _activated(store, TRIAL)
    with patch.object(store, "get_activation_state", return_value={"completed": True}):
        await handlers.handle_callback(TRIAL, 1, f"consent:{COACH_CONSENT_VERSION}")
    assert channel.last_text == "Coach is unavailable."
    assert not await store.get_proactive_consent(user["user_id"], COACH_CONSENT_VERSION)


async def test_trial_user_cannot_open_reflect_or_recommender(monkeypatch):
    monkeypatch.setattr(settings, "access_mode", "registered")
    store, channel = FakeStore(), FakeChannel()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler(), _live_runtime())
    await _activated(store, TRIAL)
    await _send(handlers, store, TRIAL, "/mode")
    assert "/mode coach" in channel.last_text
    assert "/mode reflect" not in channel.last_text
    await _send(handlers, store, TRIAL, "/mode recommender")
    assert "isn't available on your account" in channel.last_text


async def test_crisis_routing_still_fires_for_full_access(monkeypatch):
    monkeypatch.setattr(settings, "access_mode", "registered")
    store, channel = FakeStore(), FakeChannel()
    runtime = _live_runtime()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler(), runtime)
    await _activated(store, FULL)

    async def reply(messages, info):
        raise AssertionError("crisis text must not reach the model")

    async with runtime.override(model=FunctionModel(reply)):
        await _send(handlers, store, FULL, "/mode reflect")
        await _send(handlers, store, FULL, "I am thinking about suicide")
    assert "emergency" in channel.last_text.lower()


async def test_coach_is_live_and_routes_to_its_evaluated_model(monkeypatch):
    from src.agent.runtime import default_runtime

    monkeypatch.setattr(settings, "dev_model", "")
    monkeypatch.setattr(settings, "mode_models", "")
    monkeypatch.setattr(settings, "participant_model_pins", "")
    coach = build_registry()["coach"]
    assert coach.status == "live"
    reference = await default_runtime.model_for(mode=coach, resolve_only=True)
    assert reference == "google:gemini-3.8-flash"
    assert build_registry()["reflect"].status == "planned"
    assert build_registry()["recommender"].status == "planned"


async def test_modes_api_shows_coach_open_pending_consent_for_trial_users(monkeypatch):
    import httpx
    from fastapi import FastAPI

    from src.api.dependencies import get_activated_user, get_store
    from src.api.modes import router

    monkeypatch.setattr(settings, "coach_trial_enabled", True)
    store = FakeStore()
    user = await _activated(store, TRIAL)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_activated_user] = lambda: user
    app.dependency_overrides[get_store] = lambda: store
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        before = {row["id"]: row for row in (await client.get("/api/modes")).json()["modes"]}
        await store.set_coaching_consent(user["user_id"], COACH_CONSENT_VERSION)
        after = {row["id"]: row for row in (await client.get("/api/modes")).json()["modes"]}

    assert before["coach"]["available"] and before["coach"]["consent_required"]
    assert after["coach"]["available"] and not after["coach"]["consent_required"]
    assert not before["reflect"]["available"]


async def test_a_telegram_turn_admits_its_mode_once(monkeypatch):
    monkeypatch.setattr(settings, "access_mode", "registered")
    store, channel = FakeStore(), FakeChannel()
    runtime = _live_runtime()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler(), runtime)
    await _activated(store, FULL)
    resolved = []
    original = runtime.resolve

    async def counting(context, requested_mode):
        resolved.append(requested_mode)
        return await original(context, requested_mode)

    monkeypatch.setattr(runtime, "resolve", counting)

    async def reply(messages, info):
        return ModelResponse(parts=[TextPart("Fictional reply")])

    async with runtime.override(model=FunctionModel(reply)):
        await _send(handlers, store, FULL, "plan my morning")
    assert channel.last_text == "Fictional reply"
    assert len(resolved) == 1
