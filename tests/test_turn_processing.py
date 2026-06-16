"""Turn processing integration tests."""

from unittest.mock import patch

from pydantic_ai.models.test import TestModel

from src.agent.agent import amigo_agent
from src.bot.handlers import BotHandlers
from src.memory.sessions import SessionManager
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


async def test_onboarded_user_gets_agent_response():
    """An onboarded user's message should go through the agent and produce a response."""
    store = FakeStore()
    channel = FakeChannel()
    scheduler = FakeScheduler()
    handlers = BotHandlers(channel, store, SessionManager(store), scheduler)
    user = await store.create_user(123)
    await store.update_user(
        user["user_id"],
        {
            "name": "Dev",
            "timezone": "Asia/Kathmandu",
            "onboarding_complete": True,
            "onboarding_step": 3,
        },
    )

    with (
        patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True),
        amigo_agent.override(model=TestModel()),
    ):
        await handlers.handle_message(123, "hello amigo")

    # Should have sent a response
    assert len(channel.sent) >= 1
    assert len(channel.last_text) > 0


async def test_close_signal_closes_session():
    """A close signal like 'goodnight' should close the session."""
    store = FakeStore()
    channel = FakeChannel()
    scheduler = FakeScheduler()
    handlers = BotHandlers(channel, store, SessionManager(store), scheduler)
    user = await store.create_user(123)
    await store.update_user(
        user["user_id"],
        {
            "name": "Dev",
            "timezone": "Asia/Kathmandu",
            "onboarding_complete": True,
            "onboarding_step": 3,
        },
    )

    with patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True):
        await handlers.handle_message(123, "goodnight")

    assert "night" in channel.last_text.lower() or "🌙" in channel.last_text
