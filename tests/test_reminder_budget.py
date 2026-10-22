"""Participant requests never consume or get refused by the proactive message budget."""

import asyncio
import copy
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.activation import ACTIVATION_POLICY_VERSION
from src.memory.memory_store import InMemoryStore
from tests.fakes import FakeStore

AT = "2026-10-22T13:00:00+00:00"
TOMORROW = "2026-10-23T13:00:00+00:00"


@pytest.fixture(params=[InMemoryStore, FakeStore])
async def local(request, monkeypatch):
    now = datetime(2026, 10, 22, 12)
    for path in [
        "src.memory.memory_store.utc_now",
        "tests.fakes.utc_now",
        "src.memory.proactive.utc_now",
    ]:
        monkeypatch.setattr(path, lambda: now)
    store = request.param()
    user = await store.create_user(19001)
    await store.update_user(user["user_id"], {"timezone": "UTC", "daily_message_budget": 1})
    return store, user["user_id"]


def containers(store):
    prefix = "" if isinstance(store, FakeStore) else "_"
    return {
        name: getattr(store, prefix + name)
        for name in [
            "reminders",
            "tasks",
            "scheduler_outbox",
            "command_receipts",
            "reminder_occurrences",
            "reminder_delivery_attempts",
            "activation_journeys",
        ]
    }


def rows(container):
    return list(container.values()) if isinstance(container, dict) else container


async def task(store, user, name="Task"):
    return await store.create_task(user, name)


async def schedule(store, user, task_id, *, key="schedule", at=AT, replace=None):
    return await store.schedule_reminder_command(
        user_id=user,
        idempotency_key=key,
        payload_hash=key,
        task_id=task_id,
        replace_reminder_id=replace,
        scheduled_time=at,
        intended_local_date=at[:10],
        intended_local_time="13:00:00",
        intended_timezone="UTC",
    )


async def test_requested_reminders_never_count_even_when_proactive_budget_is_zero(local):
    store, user = local
    await store.update_user(user, {"daily_message_budget": 0})
    items = [await task(store, user, str(i)) for i in range(8)]
    outcomes = await asyncio.gather(*(store.create_reminder(t["task_id"], user, AT) for t in items))
    assert len(outcomes) == 8
    assert len(rows(containers(store)["reminders"])) == 8
    assert store._proactive_state.reservations == {}


async def test_full_proactive_budget_does_not_refuse_reschedule_or_later(local):
    store, user = local
    await store.reserve_proactive_delivery(user, "full", "recovery", AT)
    await store.reserve_proactive_delivery(user, "full-tomorrow", "recovery", TOMORROW)
    row = await task(store, user)
    old = (await schedule(store, user, row["task_id"], key="old"))["reminder"]
    replacement = await schedule(store, user, None, key="replace", replace=old["reminder_id"])
    assert replacement["reminder"]["reminder_id"] != old["reminder_id"]
    await store.update_reminder(replacement["reminder"]["reminder_id"], {"status": "sent"}, user)
    later = await store.apply_later_command(
        user_id=user,
        idempotency_key="later",
        payload_hash="later",
        reminder_id=replacement["reminder"]["reminder_id"],
        expected_task_version=next(
            t for t in rows(containers(store)["tasks"]) if t["task_id"] == row["task_id"]
        )["version"],
        step=1,
        scheduled_at="2026-10-22T14:00:00+00:00",
        intended_local_date="2026-10-22",
        intended_local_time="14:00:00",
        timezone="UTC",
        quiet_hours_adjusted=False,
        task_due_date="2026-10-22",
    )
    assert later
    assert len(store._proactive_state.reservations) == 2


async def test_activation_reminder_ignores_zero_budget(local):
    store, user = local
    auth = "activation-budget"
    await store.acknowledge_activation_terms(auth, ACTIVATION_POLICY_VERSION)
    await store.update_user(user, {"supabase_auth_id": auth, "daily_message_budget": 0})
    await store.update_activation_profile(
        auth, name="Test", timezone="UTC", wake_time="07:00", sleep_time="23:00"
    )
    result = await store.create_activation_test_command(
        user_id=user,
        idempotency_key="test",
        payload_hash="test",
        title="Private test",
        retry=False,
        scheduled_time=AT,
        intended_local_date="2026-10-22",
        intended_local_time="13:00:00",
        intended_timezone="UTC",
    )
    assert result["reminder"]
    assert store._proactive_state.reservations == {}


async def test_legacy_reminder_capacity_removed_without_touching_commitment(local):
    store, user = local
    row = await task(store, user)
    reminder = await store.create_reminder(row["task_id"], user, AT)
    before = copy.deepcopy(reminder)
    store._proactive_state.reservations[user, "legacy"] = dict(
        user_id=user,
        delivery_key="legacy",
        kind="reminder",
        state="accepted",
        legacy_debt=True,
        scheduled_at=AT,
        local_day=AT[:10],
        timezone="UTC",
    )
    reserved = await store.reserve_proactive_delivery(user, "recovery", "recovery", AT)
    assert reserved["status"] == "reserved"
    assert (user, "legacy") not in store._proactive_state.reservations
    assert reminder == before


async def test_recovery_capacity_fenced_owner_filtered_and_never_replayed(local):
    store, user = local
    # Fixture now12:00; the reservation represents this day's recovery batch.
    await store.reserve_proactive_delivery(user, "recovery", "recovery", AT)
    other = await store.create_user(19002)
    assert not await store.mark_proactive_dispatch(other["user_id"], "recovery")
    results = await asyncio.gather(
        *(store.mark_proactive_dispatch(user, "recovery") for _ in range(4))
    )
    assert results.count(True) == 1
    assert not await store.release_proactive_delivery(user, "recovery")
    assert not await store.finish_proactive_delivery(other["user_id"], "recovery", "accepted")
    assert await store.finish_proactive_delivery(user, "recovery", "uncertain")
    assert not await store.finish_proactive_delivery(user, "recovery", "accepted")
    assert (await store.reserve_proactive_delivery(user, "next", "recovery", AT))[
        "status"
    ] == "budget_exhausted"


async def test_budget_drop_cancels_undispatched_recovery(local):
    store, user = local
    await store.reserve_proactive_delivery(user, "recovery", "recovery", AT)
    await store.update_user(user, {"daily_message_budget": 0})
    assert not await store.mark_proactive_dispatch(user, "recovery")
    assert store._proactive_state.reservations[user, "recovery"]["state"] == "cancelled"


async def test_requested_reminder_kind_cannot_be_reserved(local):
    store, user = local
    with pytest.raises(ValueError):
        await store.reserve_proactive_delivery(user, "requested", "reminder", AT)


async def test_immutable_schedule_requires_reschedule_and_accepts_same_instant(local):
    store, user = local
    row = await task(store, user)
    reminder = await store.create_reminder(row["task_id"], user, AT)
    await store.update_reminder(
        reminder["reminder_id"], {"scheduled_time": "2026-10-22T14:00:00+01:00"}, user
    )
    before = copy.deepcopy(containers(store))
    with pytest.raises(ValueError, match="reschedule"):
        await store.update_reminder(reminder["reminder_id"], {"scheduled_time": TOMORROW}, user)
    assert containers(store) == before


async def tool_context(store, user_id, monkeypatch):
    from src.tools.context import ToolContext
    from src.utils import Clock
    from tests.fakes import FakeChannel, FakeScheduler

    monkeypatch.setattr(Clock, "utc_now", lambda self: datetime(2026, 10, 22, 12))
    user = await store.get_user_by_id(user_id)
    session = await store.create_session(user_id)
    return SimpleNamespace(
        deps=ToolContext(
            store=store,
            scheduler=FakeScheduler(),
            channel=FakeChannel(),
            user=user,
            session_id=session["session_id"],
            chat_id=19001,
            timezone="UTC",
            turn_id="budget-tool",
        )
    )


async def sent_reminder(store, user_id):
    row = await task(store, user_id, "Original task")
    reminder = await store.create_reminder(row["task_id"], user_id, AT)
    await store.update_reminder(reminder["reminder_id"], {"status": "sent"}, user_id)
    return row, reminder


async def test_create_task_tool_schedules_despite_zero_budget(local, monkeypatch):
    from src.tools.toolsets import create_task

    store, user = local
    await store.update_user(user, {"daily_message_budget": 0})
    ctx = await tool_context(store, user, monkeypatch)
    result = await create_task(ctx, "Read fictional book", reminder_time="in 90 minutes")
    assert "with reminder" in result
    assert len(rows(containers(store)["reminders"])) == 1
    assert rows(containers(store)["scheduler_outbox"])


@pytest.mark.parametrize("tool_name", ["schedule_reminder", "apply_later"])
async def test_reminder_tools_succeed_despite_full_proactive_budget(local, monkeypatch, tool_name):
    from src.tools import toolsets

    store, user = local
    ctx = await tool_context(store, user, monkeypatch)
    row, reminder = await sent_reminder(store, user)
    await store.reserve_proactive_delivery(user, "full", "recovery", AT)
    if tool_name == "schedule_reminder":
        result = await toolsets.schedule_reminder(ctx, row["task_id"], "in 90 minutes")
        assert "Reminder scheduled" in result
    else:
        result = await toolsets.apply_later(ctx, reminder["reminder_id"])
        assert "Next reminder" in result
    assert rows(containers(store)["scheduler_outbox"])
    assert len(store._proactive_state.reservations) == 1


@pytest.mark.parametrize("first,second", [("coaching", "recovery"), ("recovery", "coaching")])
async def test_only_coach_and_recovery_compete_for_shared_capacity(local, first, second):
    store, user = local
    assert (await store.reserve_proactive_delivery(user, "first", first, AT))[
        "status"
    ] == "reserved"
    assert (await store.reserve_proactive_delivery(user, "second", second, AT))[
        "status"
    ] == "budget_exhausted"
    row = await task(store, user)
    assert await store.create_reminder(row["task_id"], user, AT)
    assert len(store._proactive_state.reservations) == 1


@pytest.mark.parametrize("operation", ["mark_proactive_dispatch", "finish_proactive_delivery"])
async def test_recovery_rpc_adapter_forwards_only_owned_metadata(operation):
    from unittest.mock import AsyncMock

    from src.memory.store import MemoryStore

    store = MemoryStore()
    store._coaching_rpc = AsyncMock(return_value=True)
    args = ("owner", "recovery:key") + (
        ("uncertain",) if operation == "finish_proactive_delivery" else ()
    )
    assert await getattr(store, operation)(*args) is True
    params = dict(p_user_id="owner", p_delivery_key="recovery:key")
    if operation == "finish_proactive_delivery":
        params["p_outcome"] = "uncertain"
    store._coaching_rpc.assert_awaited_once_with(operation, params)
