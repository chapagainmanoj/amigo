"""Allowlist tests — test #5.

Unknown chat IDs should get a neutral rejection message
and never touch the store, model, or session logic.
"""

from unittest.mock import patch

import pytest

from src.agent.amigo import AmigoAgent
from src.bot.handlers import BotHandlers
from src.memory.sessions import SessionManager
from tests.fakes import FakeChannel, FakeModel, FakeScheduler, FakeStore


@pytest.fixture
def setup():
    store = FakeStore()
    channel = FakeChannel()
    model = FakeModel()
    agent = AmigoAgent(model, store)
    session_mgr = SessionManager(store)
    scheduler = FakeScheduler()
    handlers = BotHandlers(agent, channel, store, session_mgr, scheduler)
    return handlers, channel, store, model


class TestAllowlist:
    """Allowlist check should happen before any DB or LLM interaction."""

    @pytest.mark.asyncio
    async def test_unknown_chat_gets_rejection(self, setup):
        handlers, channel, store, model = setup

        with patch("src.bot.handlers.BotHandlers._is_allowed", return_value=False):
            await handlers.handle_message(99999, "hello")

        assert len(channel.sent) == 1
        assert "isn't open" in channel.last_text
        # Store should never be touched
        assert 99999 not in store.users
        # Model should never be called
        assert len(model.calls) == 0

    @pytest.mark.asyncio
    async def test_allowed_chat_proceeds(self, setup):
        handlers, channel, store, model = setup

        with patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True):
            await handlers.handle_message(12345, "hello")

        # Should have created user and started onboarding
        assert 12345 in store.users

    @pytest.mark.asyncio
    async def test_empty_allowlist_allows_all(self, setup):
        handlers, *_ = setup

        with patch("src.config.settings") as mock_settings:
            mock_settings.allowed_telegram_chat_ids = ""
            assert handlers._is_allowed(99999) is True

    @pytest.mark.asyncio
    async def test_populated_allowlist_blocks_unknown(self, setup):
        handlers, *_ = setup

        with patch("src.config.settings") as mock_settings:
            mock_settings.allowed_telegram_chat_ids = "111,222"
            assert handlers._is_allowed(333) is False
            assert handlers._is_allowed(111) is True
