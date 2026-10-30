"""Channel identities, primary channel and channel update claims across all three Stores (022)."""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.memory.identities import ChannelNotLinkedError
from src.memory.memory_store import InMemoryStore
from src.memory.store import MemoryStore
from src.utils import utc_now
from tests.fakes import FakeStore


@pytest.fixture(params=[InMemoryStore, FakeStore])
def store(request):
    return request.param()


async def _token(store, auth_id: str) -> str:
    store_journeys = getattr(store, "_activation_journeys", None)
    if store_journeys is None:
        store_journeys = store.activation_journeys
    store_journeys.setdefault(auth_id, {"acknowledged_at": utc_now().isoformat()})
    token = uuid.uuid4().hex
    await store.create_pairing_token(token, auth_id, utc_now() + timedelta(minutes=10))
    return token


async def test_telegram_users_get_a_mirrored_identity_and_telegram_primary(store):
    user = await store.create_user(41001)
    assert user["primary_channel"] == "telegram"
    assert await store.list_channel_identities(user["user_id"]) == {"telegram": "41001"}
    found = await store.get_user_by_channel_identity("telegram", "41001")
    assert found["user_id"] == user["user_id"]
    await store.update_user(user["user_id"], {"telegram_chat_id": 41002})
    assert await store.list_channel_identities(user["user_id"]) == {"telegram": "41002"}
    assert await store.get_user_by_channel_identity("telegram", "41001") is None


async def test_first_app_without_telegram_creates_profile_with_that_primary(store):
    auth = str(uuid.uuid4())
    assert await store.complete_channel_pairing(
        await _token(store, auth), "fake2", "ext-1"
    ) == {"status": "paired"}
    user = await store.get_user_by_channel_identity("fake2", "ext-1")
    assert user["primary_channel"] == "fake2"
    assert user["telegram_chat_id"] is None
    assert user["supabase_auth_id"] == auth
    assert await store.get_user_by_auth_id(auth) is not None


async def test_second_app_links_to_existing_profile_and_primary_stays(store):
    auth = str(uuid.uuid4())
    user = await store.create_user(41010)
    await store.update_user(user["user_id"], {"supabase_auth_id": auth})
    token = await _token(store, auth)
    assert await store.complete_channel_pairing(token, "fake2", "ext-10") == {"status": "paired"}
    assert await store.complete_channel_pairing(token, "fake2", "ext-10") == {
        "status": "invalid_token"
    }
    assert await store.complete_channel_pairing(
        await _token(store, auth), "fake2", "ext-10"
    ) == {"status": "already_paired"}
    assert await store.list_channel_identities(user["user_id"]) == {
        "fake2": "ext-10", "telegram": "41010",
    }
    assert (await store.get_user_by_id(user["user_id"]))["primary_channel"] == "telegram"


async def test_telegram_as_second_app_links_instead_of_conflicting(store):
    auth = str(uuid.uuid4())
    await store.complete_channel_pairing(await _token(store, auth), "fake2", "ext-20")
    user = await store.get_user_by_auth_id(auth)
    assert await store.complete_pairing(await _token(store, auth), 41020) == {"status": "paired"}
    assert (await store.get_user_by_chat_id(41020))["user_id"] == user["user_id"]
    assert await store.list_channel_identities(user["user_id"]) == {
        "fake2": "ext-20", "telegram": "41020",
    }


async def test_pairing_conflicts_keep_the_token_and_identities(store):
    owner, other = str(uuid.uuid4()), str(uuid.uuid4())
    await store.complete_channel_pairing(await _token(store, owner), "fake2", "ext-30")
    token = await _token(store, other)
    assert await store.complete_channel_pairing(token, "fake2", "ext-30") == {"status": "conflict"}
    tokens = getattr(store, "_pairing_tokens", None) or store.pairing_tokens
    assert tokens[token]["consumed"] is False
    assert await store.complete_channel_pairing(
        await _token(store, owner), "fake2", "ext-31"
    ) == {"status": "conflict"}
    # An unlinked legacy Telegram profile plus a signed-in profile are two people: no merge.
    await store.create_user(41030)
    assert await store.complete_pairing(await _token(store, owner), 41030) == {"status": "conflict"}


@pytest.mark.parametrize(
    ("channel", "external_id"),
    [("telegram", "-0041"), ("telegram", "abc"), ("Fake", "x"), ("fake2", " x"), ("fake2", "")],
)
async def test_malformed_identities_are_rejected(store, channel, external_id):
    with pytest.raises(ValueError, match="invalid_channel_identity"):
        await store.complete_channel_pairing(
            await _token(store, str(uuid.uuid4())), channel, external_id
        )


async def test_primary_channel_must_be_linked(store):
    auth = str(uuid.uuid4())
    user = await store.create_user(41040)
    await store.update_user(user["user_id"], {"supabase_auth_id": auth})
    await store.complete_channel_pairing(await _token(store, auth), "fake2", "ext-40")
    assert await store.set_primary_channel(user["user_id"], "fake2") == "fake2"
    with pytest.raises(ChannelNotLinkedError):
        await store.set_primary_channel(user["user_id"], "slack")
    with pytest.raises(ChannelNotLinkedError):
        await store.update_user(user["user_id"], {"primary_channel": "slack"})
    # Unlinking the primary is refused and leaves the identity in place.
    await store.set_primary_channel(user["user_id"], "telegram")
    with pytest.raises(ChannelNotLinkedError):
        await store.update_user(user["user_id"], {"telegram_chat_id": None})
    assert (await store.list_channel_identities(user["user_id"]))["telegram"] == "41040"
    assert (await store.get_user_by_id(user["user_id"]))["primary_channel"] == "telegram"


async def test_channel_update_claims_are_per_channel_and_telegram_delegates(store):
    first = await store.claim_channel_update("fake2", "u-1", "ext-1", "message")
    assert first["claimed"] is True and first["channel"] == "fake2"
    again = await store.claim_channel_update("fake2", "u-1", "ext-1", "message")
    assert again["claimed"] is False
    assert (await store.claim_channel_update("fake3", "u-1", "ext-1", "message"))["claimed"] is True
    with pytest.raises(ValueError, match="channel_update_identity_conflict"):
        await store.claim_channel_update("fake2", "u-1", "ext-9", "message")
    done = await store.finish_channel_update("fake2", "u-1", status="completed")
    assert done["status"] == "completed" and "claimed" not in done
    assert (await store.finish_channel_update("fake2", "u-1", status="completed"))[
        "status"
    ] == "completed"
    with pytest.raises(ValueError, match="channel_update_already_finished"):
        await store.finish_channel_update("fake2", "u-1", status="failed", failure_code="x")

    telegram = await store.claim_channel_update("telegram", "9001", "41050", "message")
    assert telegram["claimed"] is True
    assert (telegram["channel"], telegram["update_id"], telegram["external_id"]) == (
        "telegram", "9001", "41050",
    )
    assert "telegram_chat_id" not in telegram
    assert (await store.claim_telegram_update(9001, 41050, "message"))["claimed"] is False


async def test_failed_profile_write_rolls_back_identities(store):
    first = await store.create_user(41060)
    second = await store.create_user(41061)
    with pytest.raises(ValueError):
        await store.update_user(second["user_id"], {"telegram_chat_id": 41060})
    assert await store.list_channel_identities(second["user_id"]) == {"telegram": "41061"}
    assert (await store.get_user_by_chat_id(41061))["user_id"] == second["user_id"]
    assert (await store.get_user_by_channel_identity("telegram", "41060"))["user_id"] == first[
        "user_id"
    ]


async def test_telegram_pairing_replays_and_conflicts_match_sql(store):
    auth = str(uuid.uuid4())
    assert await store.complete_pairing(await _token(store, auth), 41070) == {"status": "paired"}
    assert await store.complete_pairing(await _token(store, auth), 41070) == {
        "status": "already_paired"
    }
    assert await store.complete_pairing(await _token(store, auth), 41071) == {"status": "conflict"}


async def test_telegram_claims_through_channel_api_match_009(store):
    await store.claim_channel_update("telegram", "9100", "41080", "message")
    with pytest.raises(ValueError, match="telegram_update_identity_conflict"):
        await store.claim_channel_update("telegram", "9100", "41081", "message")
    for bad in [("007", "41080"), ("9101", "-01"), ("x", "41080")]:
        with pytest.raises(ValueError, match="invalid_channel_update"):
            await store.claim_channel_update("telegram", *bad, "message")
    done = await store.finish_channel_update("telegram", "9100", status="completed")
    assert done["update_id"] == "9100" and done["external_id"] == "41080"
    assert (await store.finish_channel_update("telegram", "9100", status="completed"))[
        "status"
    ] == "completed"
    with pytest.raises(ValueError, match="telegram_update_already_finished"):
        await store.finish_channel_update("telegram", "9100", status="failed", failure_code="x")


@pytest.mark.parametrize("failure_code", [None, "", "x" * 101])
async def test_failed_updates_need_a_bounded_failure_code(store, failure_code):
    await store.claim_channel_update("fake2", "u-9", "ext-9", "message")
    with pytest.raises(ValueError, match="invalid_channel_failure_code"):
        await store.finish_channel_update(
            "fake2", "u-9", status="failed", failure_code=failure_code
        )
    with pytest.raises(ValueError, match="invalid_channel_update"):
        await store.finish_channel_update("BAD", "u-9", status="completed")


async def _sending_reminder(store, chat_id: int):
    user = await store.create_user(chat_id)
    reminders = getattr(store, "_reminders", None)
    reminder_id = str(uuid.uuid4())
    row = {"reminder_id": reminder_id, "user_id": user["user_id"], "status": "sending",
           "telegram_message_id": 777}
    if reminders is not None:
        reminders[reminder_id] = row
        occurrences, attempts = store._reminder_occurrences, store._reminder_delivery_attempts
    else:
        store.reminders.append(row)
        occurrences, attempts = store.reminder_occurrences, store.reminder_delivery_attempts
    occurrences[reminder_id] = {"provider_accepted_at": None, "terminal_at": None}
    attempts["a-1"] = {"user_id": user["user_id"], "started_at": utc_now().isoformat()}
    return user["user_id"], reminder_id, row, attempts["a-1"]


async def test_local_delivery_records_channel_ref_and_validates_first(store):
    user_id, reminder_id, row, attempt = await _sending_reminder(store, 41090)
    base = dict(attempt_id="a-1", reminder_id=reminder_id, user_id=user_id, result="accepted",
                normalized_cause=None, retry_decision="do_not_retry")
    for bad in [dict(telegram_message_id=None), dict(telegram_message_id=0),
                dict(telegram_message_id=None, channel_message_ref="abc")]:
        with pytest.raises(ValueError, match="accepted_delivery_requires_message_id"):
            await store.finish_reminder_delivery(**base, **bad)
    assert row["status"] == "sending" and "finished_at" not in attempt
    await store.finish_reminder_delivery(
        **base, telegram_message_id=None, channel="fake2", channel_message_ref="m-1"
    )
    assert (row["status"], row["delivery_channel"], row["channel_message_ref"]) == (
        "sent", "fake2", "m-1",
    )
    assert row["telegram_message_id"] is None


def _supabase(data=None):
    query = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(data=data)))
    api = MemoryStore()
    api.db = SimpleNamespace(rpc=Mock(return_value=query))
    return api


async def test_supabase_store_calls_the_022_rpcs():
    api = _supabase({"status": "paired"})
    await api.complete_channel_pairing("t", "fake2", "ext-1")
    api.db.rpc.assert_called_with(
        "complete_pairing_v2", {"p_token": "t", "p_channel": "fake2", "p_external_id": "ext-1"}
    )
    with pytest.raises(ValueError, match="invalid_channel_identity"):
        await api.complete_channel_pairing("t", "telegram", "abc")

    api = _supabase({})
    await api.claim_channel_update("fake2", "u-1", "ext-1", "message")
    api.db.rpc.assert_called_with("claim_channel_update", {
        "p_channel": "fake2", "p_update_id": "u-1", "p_external_id": "ext-1",
        "p_update_kind": "message",
    })
    await api.finish_channel_update("fake2", "u-1", status="failed", failure_code="x")
    api.db.rpc.assert_called_with("finish_channel_update", {
        "p_channel": "fake2", "p_update_id": "u-1", "p_status": "failed", "p_failure_code": "x",
    })


async def test_supabase_delivery_sends_a_channel_ref_and_keeps_telegram_ids():
    api = _supabase({"attempt": {}})
    base = dict(attempt_id="a", reminder_id="r", user_id="u", result="accepted",
                normalized_cause=None, retry_decision="do_not_retry")
    await api.finish_reminder_delivery(**base, telegram_message_id=4242)
    name, params = api.db.rpc.call_args.args
    assert name == "finish_reminder_delivery_v2"
    assert (params["p_channel"], params["p_channel_message_ref"]) == ("telegram", "4242")
    await api.finish_reminder_delivery(
        **base, telegram_message_id=None, channel="fake2", channel_message_ref="m-1"
    )
    assert api.db.rpc.call_args.args[1]["p_channel_message_ref"] == "m-1"


async def test_supabase_unknown_identity_returns_none():
    query = Mock()
    for name in ("select", "eq", "maybe_single"):
        getattr(query, name).return_value = query
    query.execute = AsyncMock(return_value=None)
    api = MemoryStore()
    api.db = SimpleNamespace(table=Mock(return_value=query))
    assert await api.get_user_by_channel_identity("fake2", "nobody") is None
    query.eq.assert_any_call("channel", "fake2")
    query.eq.assert_any_call("external_id", "nobody")


async def test_supabase_profile_write_maps_unlinked_primary():
    query = Mock()
    for name in ("update", "eq"):
        getattr(query, name).return_value = query
    query.execute = AsyncMock(side_effect=RuntimeError(
        'violates foreign key constraint "user_profiles_primary_channel_linked"'
    ))
    api = MemoryStore()
    api.db = SimpleNamespace(table=Mock(return_value=query))
    with pytest.raises(ChannelNotLinkedError):
        await api.update_user("u", {"primary_channel": "slack"})


async def test_supabase_primary_channel_maps_unlinked_error():
    query = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("channel_not_linked")))
    api = MemoryStore()
    api.db = SimpleNamespace(rpc=Mock(return_value=query))
    with pytest.raises(ChannelNotLinkedError):
        await api.set_primary_channel("u", "slack")
