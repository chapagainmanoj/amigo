"""Local scheduler claims compare UTC instants, matching the TIMESTAMPTZ SQL RPC."""

import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.activation import ACTIVATION_POLICY_VERSION
from src.commands.activation import CreateActivationTestCommand
from src.commands.base import CommandContext
from src.memory.memory_store import InMemoryStore
from src.memory.store import MemoryStore
from src.utils import Clock
from tests.fakes import FakeStore

NOW = datetime(2026, 10, 22, 12)


class FixedClock(Clock):
    def __init__(self, now):
        self.now = now

    def utc_now(self):
        return self.now


@pytest.fixture(params=[InMemoryStore, FakeStore])
def local(request, monkeypatch):
    monkeypatch.setattr("src.memory.memory_store.utc_now", lambda: NOW)
    monkeypatch.setattr("tests.fakes.utc_now", lambda: NOW)
    store = request.param()
    effects = store.scheduler_outbox if isinstance(store, FakeStore) else store._scheduler_outbox
    return store, effects


@pytest.mark.parametrize("aware_clock", [False, True])
async def test_real_activation_outbox_claims_with_naive_or_aware_clock(
    local, monkeypatch, aware_clock
):
    store, _ = local
    auth_id = "activation-effect-clock"
    await store.acknowledge_activation_terms(auth_id, ACTIVATION_POLICY_VERSION)
    user = await store.create_user(12345)
    await store.update_user(user["user_id"], {"supabase_auth_id": auth_id})
    await store.update_activation_profile(
        auth_id,
        name="Test Participant",
        timezone="UTC",
        wake_time="07:00",
        sleep_time="23:00",
    )
    result = await CreateActivationTestCommand(store, FixedClock(NOW)).run(
        CommandContext(user["user_id"], "dashboard", "timestamp-activation"),
        scheduled_at=NOW.replace(tzinfo=UTC) + timedelta(minutes=2),
        timezone="UTC",
    )
    claim_now = NOW.replace(tzinfo=UTC) if aware_clock else NOW
    monkeypatch.setattr("src.memory.memory_store.utc_now", lambda: claim_now)
    monkeypatch.setattr("tests.fakes.utc_now", lambda: claim_now)
    claimed = await store.claim_scheduler_effects(25, "activation-worker")
    assert len(claimed) == 1
    assert claimed[0]["reminder_id"] == result["reminder"]["reminder_id"]
    assert claimed[0]["status"] == "processing"
    assert claimed[0]["attempts"] == 1
    assert await store.claim_scheduler_effects(25, "other-worker") == []


def effect(
    effect_id,
    *,
    created_at="2026-10-22T11:00:00",
    available_at="2026-10-22T11:00:00",
    status="pending",
    claimed_at=None,
):
    return {
        "effect_id": effect_id,
        "user_id": "participant",
        "effect_type": "schedule",
        "created_at": created_at,
        "available_at": available_at,
        "claimed_at": claimed_at,
        "status": status,
        "attempts": 1 if status == "processing" else 0,
    }


async def test_availability_compares_instants_and_legacy_utc(local):
    store, effects = local
    effects.update(
        {
            "offset-due": effect("offset-due", available_at="2026-10-22T17:45:00+05:45"),
            "legacy-due": effect("legacy-due", available_at="2026-10-22T12:00:00"),
            "z-future": effect("z-future", available_at="2026-10-22T12:00:01Z"),
            "offset-future": effect("offset-future", available_at="2026-10-22T11:00:01-01:00"),
        }
    )
    claimed = await store.claim_scheduler_effects(25, "availability-worker")
    assert {item["effect_id"] for item in claimed} == {"offset-due", "legacy-due"}
    assert effects["z-future"]["status"] == effects["offset-future"]["status"] == "pending"


@pytest.mark.parametrize("aware_clock", [False, True])
async def test_processing_lease_expiry_boundary_and_offsets(local, monkeypatch, aware_clock):
    store, effects = local
    claim_now = NOW.replace(tzinfo=UTC) if aware_clock else NOW
    monkeypatch.setattr("src.memory.memory_store.utc_now", lambda: claim_now)
    monkeypatch.setattr("tests.fakes.utc_now", lambda: claim_now)
    effects.update(
        {
            "expired-offset": effect(
                "expired-offset", status="processing", claimed_at="2026-10-22T17:39:59+05:45"
            ),
            "expired-legacy": effect(
                "expired-legacy", status="processing", claimed_at="2026-10-22T11:54:59"
            ),
            "boundary": effect("boundary", status="processing", claimed_at="2026-10-22T11:55:00Z"),
            "fresh": effect("fresh", status="processing", claimed_at="2026-10-22T12:59:00+01:00"),
        }
    )
    claimed = await store.claim_scheduler_effects(25, "recovery-worker")
    assert {item["effect_id"] for item in claimed} == {"expired-offset", "expired-legacy"}
    assert all(item["attempts"] == 2 for item in claimed)
    assert all(item["worker_id"] == "recovery-worker" for item in claimed)
    assert effects["boundary"]["attempts"] == effects["fresh"]["attempts"] == 1


async def test_oldest_first_uses_instants_not_timestamp_lexical_order(local):
    store, effects = local
    # Insert and spell timestamps in an order different from their UTC chronological order.
    effects.update(
        {
            "legacy-newer": effect("legacy-newer", created_at="2026-10-22T11:55:00"),
            "offset-older": effect("offset-older", created_at="2026-10-22T12:50:00+01:00"),
            "z-newest": effect("z-newest", created_at="2026-10-22T11:59:00Z"),
        }
    )
    claimed = await store.claim_scheduler_effects(1, "ordered-worker")
    assert [item["effect_id"] for item in claimed] == ["offset-older"]
    claimed[0]["status"] = "tampered"
    assert effects["offset-older"]["status"] == "processing"
    assert [
        item["effect_id"] for item in await store.claim_scheduler_effects(2, "next-worker")
    ] == [
        "legacy-newer",
        "z-newest",
    ]


async def test_memory_store_claim_delegates_timestamp_comparison_to_sql_rpc():
    rows = [
        effect(
            "sql-effect",
            created_at="2026-10-22T17:40:00+05:45",
            available_at="2026-10-22T11:55:00Z",
            status="processing",
            claimed_at="2026-10-22T12:00:00+00:00",
        )
    ]
    expected = copy.deepcopy(rows)
    query = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(data=rows)))
    store = MemoryStore()
    store.db = SimpleNamespace(rpc=Mock(return_value=query))
    assert await store.claim_scheduler_effects(7, "sql-worker") == expected
    store.db.rpc.assert_called_once_with(
        "claim_scheduler_outbox",
        {"p_limit": 7, "p_worker_id": "sql-worker"},
    )
    query.execute.assert_awaited_once_with()
    query.execute.return_value = SimpleNamespace(data=None)
    assert await store.claim_scheduler_effects(7, "sql-worker") == []
