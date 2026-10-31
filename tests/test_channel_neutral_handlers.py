"""The shared bot layer resolves participants by channel identity, not by Telegram chat id."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.activation import ACTIVATION_POLICY_VERSION
from src.bot.handlers import BotHandlers
from src.bot.pairing import pairing_token
from src.memory.sessions import SessionManager
from src.utils import utc_now
from tests.fakes import FakeChannel, FakeScheduler, FakeStore, complete_activation

TOKEN = f"{7:032x}"


@pytest.mark.parametrize(
    ("text", "token"),
    [
        (f"/start pair_{TOKEN}", TOKEN),
        (f"/pair {TOKEN}", TOKEN),
        (f"  /pair   {TOKEN}  ", TOKEN),
        ("/pair", ""),
        ("/start pair_not a token", "not a token"),
        (f"/PAIR {TOKEN}", TOKEN),
        (f"/pair_{TOKEN}", TOKEN),
        ("/pairing", None),
        ("pair me", None),
        ("/start", None),
    ],
)
def test_pairing_token_accepts_deep_link_and_typed_command(text, token):
    assert pairing_token(text) == token


async def _activated_telegram_user(store, chat_id=41501, auth_id="auth-41501"):
    await store.acknowledge_activation_terms(auth_id, ACTIVATION_POLICY_VERSION)
    user = await store.create_user(chat_id)
    await store.update_user(user["user_id"], {
        "supabase_auth_id": auth_id, "onboarding_complete": True,
    })
    await complete_activation(store, auth_id)
    return user, auth_id


def _handlers(store, channel):
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler())
    handlers.store.get_activation_state = AsyncMock(return_value={"completed": True})
    return handlers


@pytest.fixture
def open_access(monkeypatch):
    monkeypatch.setattr("src.config.settings.access_mode", "open")
    monkeypatch.setattr("src.config.settings.allowed_telegram_chat_ids", "41501")


async def test_second_app_pairs_with_typed_command_and_then_reaches_the_same_participant(
    open_access,
):
    store = FakeStore()
    user, auth_id = await _activated_telegram_user(store)
    await store.create_pairing_token(TOKEN, auth_id, utc_now() + timedelta(minutes=10))
    fake2 = FakeChannel(channel_id="fake2")
    handlers = _handlers(store, fake2)

    await handlers.handle_message("ext-9", f"/pair {TOKEN}", update_id=1)
    assert "fake2 is connected" in fake2.last_text
    assert await store.list_channel_identities(user["user_id"]) == {
        "fake2": "ext-9", "telegram": "41501",
    }

    # A model-free command proves the address now resolves to the activated participant.
    await handlers.handle_message("ext-9", "/help", update_id=2)
    assert fake2.sent[-1]["chat_id"] == "ext-9"
    assert "/mode" in fake2.last_text


async def test_other_apps_never_create_or_join_accounts_without_full_access(
    open_access, monkeypatch
):
    store = FakeStore()
    fake2 = FakeChannel(channel_id="fake2")
    handlers = _handlers(store, fake2)
    # No profile yet: a dashboard token (e.g. from the Telegram link) must not create one.
    await store.acknowledge_activation_terms("auth-new", ACTIVATION_POLICY_VERSION)
    await store.create_pairing_token(TOKEN, "auth-new", utc_now() + timedelta(minutes=10))
    await handlers.handle_message("ext-1", f"/pair {TOKEN}", update_id=1)
    assert "full access" in fake2.last_text
    assert await store.get_user_by_auth_id("auth-new") is None
    assert await store.get_pairing_token_owner(TOKEN) == "auth-new"  # not consumed

    # An activated Telegram account without full access cannot add another app either.
    monkeypatch.setattr("src.config.settings.allowed_telegram_chat_ids", "1")
    user, auth_id = await _activated_telegram_user(store)
    await store.create_pairing_token(f"{8:032x}", auth_id, utc_now() + timedelta(minutes=10))
    await handlers.handle_message("ext-2", f"/PAIR {8:032x}", update_id=2)
    assert "full access" in fake2.last_text
    assert await store.list_channel_identities(user["user_id"]) == {"telegram": "41501"}


async def test_telegram_chat_id_on_another_channel_is_not_that_participant(open_access):
    store = FakeStore()
    await _activated_telegram_user(store)
    fake2 = FakeChannel(channel_id="fake2")
    handlers = _handlers(store, fake2)

    # The same digits on another app are a different, unlinked address, refused even when open.
    await handlers.handle_message(41501, "/help", update_id=1)
    assert "isn't open" in fake2.last_text


@pytest.mark.parametrize("posture", ["allowlist", "registered", "invite"])
@pytest.mark.parametrize(("full_access", "allowed"), [(True, True), (False, False)])
async def test_every_posture_admits_other_apps_only_for_linked_full_access_accounts(
    posture, full_access, allowed
):
    store = FakeStore()
    user, _ = await _activated_telegram_user(store)
    store._identity_state.link(user["user_id"], "fake2", "ext-9")
    handlers = _handlers(store, FakeChannel(channel_id="fake2"))

    with patch("src.config.settings") as settings:
        settings.access_mode = posture
        settings.allowed_telegram_chat_ids = "41501" if full_access else "1"
        assert await handlers._is_allowed("ext-9") is allowed
        assert await handlers._is_allowed("unlinked") is False
        assert await handlers._is_allowed("unlinked", pairing_attempt=True) is True


async def test_expired_or_unknown_code_on_another_app_says_the_link_is_invalid(open_access):
    store = FakeStore()
    await _activated_telegram_user(store)
    fake2 = FakeChannel(channel_id="fake2")
    await _handlers(store, fake2).handle_message("ext-3", f"/pair {9:032x}", update_id=1)
    assert "invalid or has expired" in fake2.last_text


async def test_database_guard_refusal_reaches_the_participant(open_access, monkeypatch):
    """024: even past the bot's own check, the Store refuses to create an account."""
    monkeypatch.setattr("src.bot.pairing._second_app_allowed", AsyncMock(return_value=True))
    store = FakeStore()
    await store.acknowledge_activation_terms("auth-none", ACTIVATION_POLICY_VERSION)
    await store.create_pairing_token(TOKEN, "auth-none", utc_now() + timedelta(minutes=10))
    fake2 = FakeChannel(channel_id="fake2")
    await _handlers(store, fake2).handle_message("ext-4", f"/pair {TOKEN}", update_id=1)
    assert "full access" in fake2.last_text
    assert await store.get_user_by_auth_id("auth-none") is None
