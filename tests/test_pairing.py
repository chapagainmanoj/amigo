"""Tests for Telegram account pairing and linking."""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.bot.handlers import BotHandlers
from src.bot.pairing import handle_start_pairing
from src.memory.memory_store import InMemoryStore
from src.memory.pairing import PairingTokenRateLimitError
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.utils import utc_now
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


def _token(number: int) -> str:
    return f"{number:032x}"


class _FakeRpcCall:
    def __init__(self, data=None, error: Exception | None = None):
        self.data = data
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return SimpleNamespace(data=self.data)


class _FakeRpcDB:
    def __init__(self, responses: dict[str, _FakeRpcCall]):
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def rpc(self, name: str, params: dict):
        self.calls.append((name, params))
        return self.responses[name]


async def test_pairing_token_lifecycle():
    """Verify pairing token creation, consumption, and expiration/consumption rules."""
    store = FakeStore()
    auth_id = str(uuid.uuid4())
    token = _token(1)

    # Create token
    expires_at = utc_now() + timedelta(minutes=15)
    await store.create_pairing_token(token, auth_id, expires_at)

    # Token is in the store
    assert token in store.pairing_tokens
    assert store.pairing_tokens[token]["consumed"] is False
    assert store.pairing_tokens[token]["supabase_auth_id"] == auth_id

    # Consume the token only through the atomic Pairing operation.
    result = await store.complete_pairing(token, 1001)
    assert result == {"status": "paired"}
    assert store.pairing_tokens[token]["consumed"] is True

    # Try consuming it again
    assert await store.complete_pairing(token, 1001) == {"status": "invalid_token"}


async def test_pairing_token_expired():
    """Verify that expired pairing tokens cannot be consumed."""
    store = FakeStore()
    auth_id = str(uuid.uuid4())
    token = _token(2)

    # Create expired token
    expires_at = utc_now() - timedelta(seconds=1)
    await store.create_pairing_token(token, auth_id, expires_at)

    # Pairing with the token fails.
    assert await store.complete_pairing(token, 1002) == {"status": "invalid_token"}


async def test_handle_start_pairing_success():
    """Verify that handle_start_pairing successfully links an existing Telegram user."""
    store = FakeStore()
    channel = FakeChannel()
    auth_id = str(uuid.uuid4())
    chat_id = 9999
    token = _token(3)

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
    token = _token(4)

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
    token = _token(5)
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


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_replacement_token_invalidates_older_unconsumed_token(store_factory):
    store = store_factory()
    auth_id = str(uuid.uuid4())
    expires_at = utc_now() + timedelta(minutes=15)

    await store.create_pairing_token(_token(10), auth_id, expires_at)
    await store.create_pairing_token(_token(11), auth_id, expires_at)

    assert await store.complete_pairing(_token(10), 1003) == {"status": "invalid_token"}
    assert await store.complete_pairing(_token(11), 1003) == {"status": "paired"}


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_pairing_token_generation_is_rate_limited(store_factory):
    store = store_factory()
    auth_id = str(uuid.uuid4())
    expires_at = utc_now() + timedelta(minutes=15)

    for number in range(20, 25):
        await store.create_pairing_token(_token(number), auth_id, expires_at)

    with pytest.raises(PairingTokenRateLimitError):
        await store.create_pairing_token(_token(25), auth_id, expires_at)


async def test_pairing_cannot_reassign_linked_telegram_profile():
    store = FakeStore()
    channel = FakeChannel()
    chat_id = 1234
    original_auth_id = str(uuid.uuid4())
    attacker_auth_id = str(uuid.uuid4())
    user = await store.create_user(chat_id)
    await store.update_user(user["user_id"], {"supabase_auth_id": original_auth_id})
    await store.create_pairing_token(
        _token(30), attacker_auth_id, utc_now() + timedelta(minutes=15)
    )

    await handle_start_pairing(chat_id, _token(30), store, channel)

    linked_user = await store.get_user_by_chat_id(chat_id)
    assert linked_user["supabase_auth_id"] == original_auth_id
    assert "already linked" in channel.last_text.lower()


async def test_pairing_cannot_duplicate_linked_dashboard_account():
    store = FakeStore()
    channel = FakeChannel()
    auth_id = str(uuid.uuid4())
    original_chat_id = 1234
    other_chat_id = 5678
    user = await store.create_user(original_chat_id)
    await store.update_user(user["user_id"], {"supabase_auth_id": auth_id})
    await store.create_pairing_token(_token(31), auth_id, utc_now() + timedelta(minutes=15))

    await handle_start_pairing(other_chat_id, _token(31), store, channel)

    assert await store.get_user_by_chat_id(other_chat_id) is None
    assert (await store.get_user_by_auth_id(auth_id))["telegram_chat_id"] == original_chat_id
    assert "already linked" in channel.last_text.lower()


async def test_pairing_same_existing_link_is_idempotent():
    store = FakeStore()
    channel = FakeChannel()
    auth_id = str(uuid.uuid4())
    chat_id = 1234
    user = await store.create_user(chat_id)
    await store.update_user(user["user_id"], {"supabase_auth_id": auth_id})
    await store.create_pairing_token(_token(32), auth_id, utc_now() + timedelta(minutes=15))

    await handle_start_pairing(chat_id, _token(32), store, channel)

    assert len(store.users) == 1
    assert "already connected" in channel.last_text.lower()


async def test_malformed_pairing_token_is_rejected_without_logging_secret(caplog):
    store = FakeStore()
    channel = FakeChannel()
    malformed_token = "not-a-valid-token"

    await handle_start_pairing(1234, malformed_token, store, channel)

    assert await store.get_user_by_chat_id(1234) is None
    assert "invalid or has expired" in channel.last_text.lower()
    assert malformed_token not in caplog.text


async def test_memory_store_issues_token_through_atomic_rpc():
    expires_at = utc_now() + timedelta(minutes=15)
    db = _FakeRpcDB(
        {"issue_pairing_token": _FakeRpcCall(data=[{"token": _token(40)}])}
    )
    store = MemoryStore.__new__(MemoryStore)
    store.db = db

    result = await store.create_pairing_token(_token(40), "auth-id", expires_at)

    assert result == {"token": _token(40)}
    assert db.calls == [
        (
            "issue_pairing_token",
            {
                "p_token": _token(40),
                "p_auth_id": "auth-id",
                "p_expires_at": expires_at.isoformat(),
            },
        )
    ]


async def test_memory_store_maps_pairing_rate_limit_from_rpc():
    db = _FakeRpcDB(
        {
            "issue_pairing_token": _FakeRpcCall(
                error=RuntimeError("pairing_token_rate_limited")
            )
        }
    )
    store = MemoryStore.__new__(MemoryStore)
    store.db = db

    with pytest.raises(PairingTokenRateLimitError):
        await store.create_pairing_token(
            _token(41), "auth-id", utc_now() + timedelta(minutes=15)
        )


async def test_memory_store_completes_pairing_through_atomic_rpc():
    db = _FakeRpcDB({"complete_pairing": _FakeRpcCall(data={"status": "paired"})})
    store = MemoryStore.__new__(MemoryStore)
    store.db = db

    result = await store.complete_pairing(_token(42), 1234)

    assert result == {"status": "paired"}
    assert db.calls == [
        ("complete_pairing", {"p_token": _token(42), "p_telegram_chat_id": 1234})
    ]
