"""Tests for Telegram account pairing and linking."""

import uuid
from datetime import timedelta
from unittest.mock import patch

from src.bot.handlers import BotHandlers
from src.bot.pairing import handle_start_pairing
from src.memory.sessions import SessionManager
from src.utils import utc_now
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


async def test_pairing_token_lifecycle():
    """Verify pairing token creation, consumption, and expiration/consumption rules."""
    store = FakeStore()
    auth_id = str(uuid.uuid4())
    token = "test_pairing_token_123"

    # Create token
    expires_at = utc_now() + timedelta(minutes=15)
    await store.create_pairing_token(token, auth_id, expires_at)

    # Token is in the store
    assert token in store.pairing_tokens
    assert store.pairing_tokens[token]["consumed"] is False
    assert store.pairing_tokens[token]["supabase_auth_id"] == auth_id

    # Consume token
    token_row = await store.consume_pairing_token(token)
    assert token_row is not None
    assert token_row["supabase_auth_id"] == auth_id
    assert store.pairing_tokens[token]["consumed"] is True

    # Try consuming it again
    assert await store.consume_pairing_token(token) is None


async def test_pairing_token_expired():
    """Verify that expired pairing tokens cannot be consumed."""
    store = FakeStore()
    auth_id = str(uuid.uuid4())
    token = "expired_token"

    # Create expired token
    expires_at = utc_now() - timedelta(seconds=1)
    await store.create_pairing_token(token, auth_id, expires_at)

    # Consume token fails
    assert await store.consume_pairing_token(token) is None


async def test_handle_start_pairing_success():
    """Verify that handle_start_pairing successfully links an existing Telegram user."""
    store = FakeStore()
    channel = FakeChannel()
    auth_id = str(uuid.uuid4())
    chat_id = 9999
    token = "success_token"

    # Set up user and token
    await store.create_user(chat_id)
    expires_at = utc_now() + timedelta(minutes=15)
    await store.create_pairing_token(token, auth_id, expires_at)

    # Run pairing
    await handle_start_pairing(chat_id, token, store, channel)

    # User should be updated
    user = await store.get_user_by_chat_id(chat_id)
    assert user["supabase_auth_id"] == auth_id

    # Message sent
    assert "Successfully paired!" in channel.last_text


async def test_handle_start_pairing_creates_user():
    """Verify that handle_start_pairing creates a new user profile if it doesn't exist."""
    store = FakeStore()
    channel = FakeChannel()
    auth_id = str(uuid.uuid4())
    chat_id = 8888
    token = "new_user_token"

    # Set up token (no user exists yet)
    expires_at = utc_now() + timedelta(minutes=15)
    await store.create_pairing_token(token, auth_id, expires_at)

    # Run pairing
    await handle_start_pairing(chat_id, token, store, channel)

    # User profile should have been created and linked
    user = await store.get_user_by_chat_id(chat_id)
    assert user is not None
    assert user["supabase_auth_id"] == auth_id
    assert "Successfully paired!" in channel.last_text


async def test_bot_handler_routes_pairing():
    """Verify that BotHandlers routes /start pair_<token> commands through to the pairing logic."""
    store = FakeStore()
    channel = FakeChannel()
    scheduler = FakeScheduler()
    handlers = BotHandlers(channel, store, SessionManager(store), scheduler)

    chat_id = 7777
    token = "deep_link_token"
    auth_id = str(uuid.uuid4())

    expires_at = utc_now() + timedelta(minutes=15)
    await store.create_pairing_token(token, auth_id, expires_at)

    with patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True):
        await handlers.handle_message(chat_id, f"/start pair_{token}")

    # Pairing should have completed
    user = await store.get_user_by_chat_id(chat_id)
    assert user is not None
    assert user["supabase_auth_id"] == auth_id
    assert "Successfully paired!" in channel.last_text
