"""Access tiers: allowlisted full access, a bounded trial for everyone else."""

from unittest.mock import patch

import pytest
from pydantic_ai.models.test import TestModel

from src.access import help_message, is_full_access, trial_exhausted
from src.agent.runtime import default_runtime
from src.bot.handlers import BotHandlers
from src.config import settings
from src.memory.memory_store import InMemoryStore
from src.memory.sessions import SessionManager
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


async def _activated(store, chat_id=123):
    user = await store.create_user(chat_id)
    await store.update_user(
        user["user_id"],
        {
            "timezone": "UTC",
            "onboarding_complete": True,
            "onboarding_step": 3,
            "supabase_auth_id": f"auth-{chat_id}",
        },
    )
    return await store.get_user_by_chat_id(chat_id)


async def _seed_messages(store, user, count):
    session = await store.create_session(user["user_id"])
    for _ in range(count):
        await store.add_message(session["session_id"], user["user_id"], "user", "hi")
        await store.add_message(session["session_id"], user["user_id"], "assistant", "hey")


@pytest.mark.parametrize("store_cls", [FakeStore, InMemoryStore])
async def test_count_participant_messages_counts_only_own_user_messages(store_cls):
    store = store_cls()
    user = await _activated(store, 1)
    other = await _activated(store, 2)
    await _seed_messages(store, user, 3)
    await _seed_messages(store, other, 5)

    assert await store.count_participant_messages(user["user_id"]) == 3


def test_full_access_follows_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "allowed_telegram_chat_ids", "123, 456")
    assert is_full_access(123)
    assert is_full_access("456")
    assert not is_full_access(789)
    assert not is_full_access(None)


@pytest.mark.parametrize(("used", "exhausted"), [(29, False), (30, True), (31, True)])
async def test_trial_boundary(monkeypatch, used, exhausted):
    monkeypatch.setattr(settings, "allowed_telegram_chat_ids", "")
    monkeypatch.setattr(settings, "trial_message_limit", 30)
    store = FakeStore()
    user = await _activated(store)
    await _seed_messages(store, user, used)

    assert await trial_exhausted(store, user) is exhausted


async def test_full_access_has_no_cap(monkeypatch):
    monkeypatch.setattr(settings, "allowed_telegram_chat_ids", "123")
    store = FakeStore()
    user = await _activated(store)
    await _seed_messages(store, user, 500)

    assert await trial_exhausted(store, user) is False


async def _send(handlers, store, text):
    with (
        patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True),
        patch.object(store, "get_activation_state", return_value={"completed": True}),
    ):
        await handlers.handle_message(123, text)


async def test_finished_trial_replies_without_model_or_storage(monkeypatch):
    monkeypatch.setattr(settings, "allowed_telegram_chat_ids", "")
    monkeypatch.setattr(settings, "trial_message_limit", 2)
    monkeypatch.setattr(settings, "trial_contact", "hello@example.com")
    store = FakeStore()
    channel = FakeChannel()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler())
    user = await _activated(store)
    await _seed_messages(store, user, 2)
    before = len(store.messages)

    with patch.object(
        handlers.turn_processor.turn_orchestrator, "handle_turn",
        side_effect=AssertionError("model must not run"),
    ):
        await _send(handlers, store, "remind me to call mom at 6")

    assert "trial has finished" in channel.last_text
    assert "hello@example.com" in channel.last_text
    assert "123" in channel.last_text
    assert len(store.messages) == before


async def test_trial_turns_count_until_limit(monkeypatch):
    monkeypatch.setattr(settings, "allowed_telegram_chat_ids", "")
    monkeypatch.setattr(settings, "trial_message_limit", 2)
    store = FakeStore()
    channel = FakeChannel()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler())
    await _activated(store)

    async with default_runtime.override(model=TestModel()):
        await _send(handlers, store, "hello")
        await _send(handlers, store, "what's on today")
        await _send(handlers, store, "one more")

    assert "trial has finished" in channel.last_text
    assert sum(1 for row in store.messages if row["role"] == "user") == 2


async def test_commands_stay_available_after_trial(monkeypatch):
    monkeypatch.setattr(settings, "allowed_telegram_chat_ids", "")
    monkeypatch.setattr(settings, "trial_message_limit", 1)
    store = FakeStore()
    channel = FakeChannel()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler())
    user = await _activated(store)
    await _seed_messages(store, user, 1)

    await _send(handlers, store, "/help")
    assert channel.last_text == help_message()
    assert settings.guide_url in channel.last_text

    await _send(handlers, store, "/mode")
    assert "trial has finished" not in channel.last_text
    assert await store.count_participant_messages(user["user_id"]) == 1


async def test_allowlisted_user_continues_past_limit(monkeypatch):
    monkeypatch.setattr(settings, "allowed_telegram_chat_ids", "123")
    monkeypatch.setattr(settings, "trial_message_limit", 1)
    store = FakeStore()
    channel = FakeChannel()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler())
    user = await _activated(store)
    await _seed_messages(store, user, 5)

    async with default_runtime.override(model=TestModel()):
        await _send(handlers, store, "hello")

    assert "trial has finished" not in channel.last_text
    assert await store.count_participant_messages(user["user_id"]) == 6


@pytest.mark.parametrize("mode", ["registered", "invite"])
async def test_registered_and_invite_admit_the_same(monkeypatch, mode):
    monkeypatch.setattr(settings, "access_mode", mode)
    store = FakeStore()
    handlers = BotHandlers(FakeChannel(), store, SessionManager(store), FakeScheduler())
    await _activated(store)

    assert await handlers._is_allowed(123)
    assert not await handlers._is_allowed(999)
    assert await handlers._is_allowed(999, pairing_attempt=True)
