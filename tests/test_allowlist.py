"""Allowlist tests — test #5.

Unknown chat IDs should get a neutral rejection message
and never touch the store, model, or session logic.
"""

from unittest.mock import patch

import pytest

from src.bot.handlers import BotHandlers
from src.memory.sessions import SessionManager
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


@pytest.fixture
def setup():
    store = FakeStore()
    channel = FakeChannel()
    session_mgr = SessionManager(store)
    scheduler = FakeScheduler()
    handlers = BotHandlers(channel, store, session_mgr, scheduler)
    return handlers, channel, store


class TestAllowlist:
    """Allowlist check should happen before any DB or LLM interaction."""

    @pytest.mark.asyncio
    async def test_unknown_chat_gets_rejection(self, setup):
        handlers, channel, store = setup

        with patch("src.bot.handlers.BotHandlers._is_allowed", return_value=False):
            await handlers.handle_message(99999, "hello")

        assert len(channel.sent) == 1
        assert "isn't open" in channel.last_text
        # Store should never be touched
        assert 99999 not in store.users

    @pytest.mark.asyncio
    async def test_allowed_chat_proceeds(self, setup):
        handlers, channel, store = setup

        with patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True):
            await handlers.handle_message(12345, "hello")

        # Should have created user and started onboarding
        assert 12345 in store.users

    @pytest.mark.asyncio
    async def test_empty_allowlist_allows_all(self, setup):
        handlers, *_ = setup

        with patch("src.config.settings") as mock_settings:
            mock_settings.access_mode = "open"
            mock_settings.allowed_telegram_chat_ids = ""
            assert await handlers._is_allowed(99999) is True

    @pytest.mark.asyncio
    async def test_populated_allowlist_blocks_unknown(self, setup):
        handlers, *_ = setup

        with patch("src.config.settings") as mock_settings:
            mock_settings.access_mode = "allowlist"
            mock_settings.allowed_telegram_chat_ids = "111,222"
            assert await handlers._is_allowed(333) is False
            assert await handlers._is_allowed(111) is True

    @pytest.mark.asyncio
    async def test_closed_mode_blocks_messages_and_callbacks(self, setup):
        handlers, channel, store = setup

        with patch("src.config.settings") as mock_settings:
            mock_settings.access_mode = "closed"
            await handlers.handle_message(111, "hello")
            await handlers.handle_callback(111, 1, "done:guessed-task")

        assert len(channel.sent) == 2
        assert 111 not in store.users
        assert store.tasks == []

    @pytest.mark.asyncio
    async def test_invite_mode_allows_pairing_and_paired_profiles_only(self, setup):
        handlers, *_channel, store = setup
        paired = await store.create_user(111)
        await store.update_user(paired["user_id"], {"supabase_auth_id": "auth-user"})

        with patch("src.config.settings") as mock_settings:
            mock_settings.access_mode = "invite"
            assert await handlers._is_allowed(222, pairing_attempt=True) is True
            assert await handlers._is_allowed(111) is True
            assert await handlers._is_allowed(222) is False

    @pytest.mark.asyncio
    async def test_malformed_allowlist_fails_closed(self, setup, caplog):
        handlers, *_ = setup

        with patch("src.config.settings") as mock_settings:
            mock_settings.access_mode = "allowlist"
            mock_settings.allowed_telegram_chat_ids = "111,not-an-id"
            assert await handlers._is_allowed(111) is False

        assert "ALLOWED_TELEGRAM_CHAT_IDS" in caplog.text
        assert "not-an-id" not in caplog.text
