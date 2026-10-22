"""Reminder admission is atomic with the same local-day budget used by Coach deliveries."""

import asyncio
import copy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.activation import ACTIVATION_POLICY_VERSION
from src.commands.base import ProactiveBudgetExceeded
from src.memory.memory_store import InMemoryStore
from src.memory.proactive import reminder_budget_transaction
from src.memory.store import MemoryStore
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


async def test_direct_reminder_creation_refuses_full_shared_budget_and_has_no_partial_row(local):
    store, user = local
    first_task, second_task = await task(store, user, "First"), await task(store, user, "Second")
    first = await store.create_reminder(first_task["task_id"], user, AT)
    before = copy.deepcopy(containers(store))
    with pytest.raises(ProactiveBudgetExceeded):
        await store.create_reminder(second_task["task_id"], user, AT)
    assert containers(store) == before
    reservation = store._proactive_state.reservations[user, f"reminder:{first['reminder_id']}"]
    assert reservation["state"] == "reserved" and not reservation["legacy_debt"]


async def test_default_four_slots_are_serialized_across_concurrent_reminder_requests(local):
    store, user = local
    await store.update_user(user, {"daily_message_budget": None})
    tasks = [await task(store, user, str(index)) for index in range(5)]
    outcomes = await asyncio.gather(
        *(store.create_reminder(row["task_id"], user, AT) for row in tasks), return_exceptions=True
    )
    assert sum(isinstance(row, dict) for row in outcomes) == 4
    assert sum(isinstance(row, ProactiveBudgetExceeded) for row in outcomes) == 1
    assert len(rows(containers(store)["reminders"])) == 4
    assert len(store._proactive_state.reservations) == 4


async def test_coaching_and_reminder_reservations_compete_for_the_same_slot(local):
    store, user = local
    draft = await store.draft_coaching_program(
        user,
        "draft",
        "draft",
        goal="Walk",
        success_measure="Three walks",
        check_in_days=[4],
        check_in_time="13:00",
        timezone="UTC",
    )
    program = draft["program"]["program_id"]
    reserved = await store.reserve_proactive_delivery(user, "coach:one", "coaching", AT, program)
    assert reserved["status"] == "reserved"
    row = await task(store, user)
    with pytest.raises(ProactiveBudgetExceeded):
        await schedule(store, user, row["task_id"])
    assert not rows(containers(store)["reminders"])
    assert await store.release_proactive_delivery(user, "coach:one")
    await schedule(store, user, row["task_id"])
    assert (await store.reserve_proactive_delivery(user, "coach:two", "coaching", AT, program))[
        "status"
    ] == "budget_exhausted"


async def test_reschedule_refusal_rolls_back_old_task_reminder_outbox_and_receipt(local):
    store, user = local
    row = await task(store, user)
    old = (await schedule(store, user, row["task_id"], key="old"))["reminder"]
    await store.reserve_proactive_delivery(user, "next-day:occupied", "recovery", TOMORROW)
    before = copy.deepcopy(containers(store))
    ledger = copy.deepcopy(store._proactive_state.reservations)
    with pytest.raises(ProactiveBudgetExceeded):
        await schedule(store, user, None, key="replace", at=TOMORROW, replace=old["reminder_id"])
    assert containers(store) == before
    assert store._proactive_state.reservations == ledger
    assert await store.release_proactive_delivery(user, "next-day:occupied")
    result = await schedule(
        store, user, None, key="replace", at=TOMORROW, replace=old["reminder_id"]
    )
    assert result["reminder"]["scheduled_time"] == TOMORROW
    assert (
        await schedule(store, user, None, key="replace", at=TOMORROW, replace=old["reminder_id"])
        == result
    )


async def test_pending_reschedule_releases_unsent_slot_but_sent_reminder_does_not(local):
    store, user = local
    row = await task(store, user)
    old = await store.create_reminder(row["task_id"], user, AT)
    result = await schedule(store, user, None, key="replacement", replace=old["reminder_id"])
    reminder = result["reminder"]
    assert (
        store._proactive_state.reservations[user, f"reminder:{old['reminder_id']}"]["state"]
        == "cancelled"
    )
    await store.update_reminder(reminder["reminder_id"], {"status": "sent"}, user)
    before = copy.deepcopy(containers(store))
    with pytest.raises(ProactiveBudgetExceeded):
        await schedule(store, user, None, key="sent-replacement", replace=reminder["reminder_id"])
    assert containers(store) == before
    assert (
        store._proactive_state.reservations[user, f"reminder:{reminder['reminder_id']}"]["state"]
        == "accepted"
    )


async def test_later_budget_refusal_preserves_sent_reminder_task_and_outbox(local):
    store, user = local
    row = await task(store, user)
    old = await store.create_reminder(row["task_id"], user, AT)
    await store.update_reminder(old["reminder_id"], {"status": "sent"}, user)
    before = copy.deepcopy(containers(store))
    with pytest.raises(ProactiveBudgetExceeded):
        await store.apply_later_command(
            user_id=user,
            idempotency_key="later",
            payload_hash="later",
            reminder_id=old["reminder_id"],
            expected_task_version=row["version"],
            step=1,
            scheduled_at="2026-10-22T14:00:00+00:00",
            intended_local_date="2026-10-22",
            intended_local_time="14:00:00",
            timezone="UTC",
            quiet_hours_adjusted=False,
            task_due_date="2026-10-22",
        )
    assert containers(store) == before
    assert old["status"] == "sent" or isinstance(store, InMemoryStore)


async def test_activation_budget_refusal_rolls_back_its_private_task_journey_and_receipt(local):
    store, user = local
    auth = "activation-budget"
    await store.acknowledge_activation_terms(auth, ACTIVATION_POLICY_VERSION)
    await store.update_user(user, {"supabase_auth_id": auth})
    await store.update_activation_profile(
        auth, name="Test", timezone="UTC", wake_time="07:00", sleep_time="23:00"
    )
    occupied = await task(store, user)
    await store.create_reminder(occupied["task_id"], user, AT)
    before = copy.deepcopy(containers(store))
    with pytest.raises(ProactiveBudgetExceeded):
        await store.create_activation_test_command(
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
    assert containers(store) == before


@pytest.mark.parametrize(
    "status,message_id,claimed,expected",
    [
        ("pending", 77, False, "accepted"),
        ("acknowledged", 77, False, "accepted"),
        ("pending", None, True, "uncertain"),
        ("cancelled", None, True, "uncertain"),
    ],
)
async def test_legacy_accepted_or_attempted_slot_survives_cancel(
    local, status, message_id, claimed, expected
):
    store, user = local
    row = await task(store, user)
    old = await store.create_reminder(row["task_id"], user, AT)
    data = containers(store)
    raw = next(
        item for item in rows(data["reminders"]) if item["reminder_id"] == old["reminder_id"]
    )
    raw.update(status=status, telegram_message_id=message_id)
    # Trusted legacy-cutover fixture: bypass normal mutations deliberately.
    store._proactive_state.reservations.clear()
    if claimed:
        data["reminder_occurrences"][old["reminder_id"]] = {
            "occurrence_id": "legacy",
            "first_claimed_at": AT,
        }
    await store.cancel_reminder_command(
        user_id=user,
        idempotency_key="cancel",
        payload_hash="cancel",
        reminder_id=old["reminder_id"],
    )
    assert (
        store._proactive_state.reservations[user, f"reminder:{old['reminder_id']}"]["state"]
        == expected
    )
    with pytest.raises(ProactiveBudgetExceeded):
        await store.create_reminder(row["task_id"], user, AT)


async def test_delivery_claim_consumes_slot_and_acknowledgment_cannot_release_it(local):
    store, user = local
    row = await task(store, user)
    reminder = await store.create_reminder(row["task_id"], user, AT)
    claim = await store.claim_reminder_for_send(reminder["reminder_id"], user, "delivery")
    key = (user, f"reminder:{reminder['reminder_id']}")
    assert store._proactive_state.reservations[key]["state"] == "dispatched"
    await store.finish_reminder_delivery(
        attempt_id=claim["attempt"]["attempt_id"],
        reminder_id=reminder["reminder_id"],
        user_id=user,
        result="accepted",
        normalized_cause=None,
        retry_decision="do_not_retry",
        telegram_message_id=88,
    )
    await store.resolve_task_command(
        user_id=user,
        idempotency_key="done",
        payload_hash="done",
        task_id=row["task_id"],
        outcome="completed",
        expected_version=row["version"],
        acted_reminder_id=reminder["reminder_id"],
    )
    assert store._proactive_state.reservations[key]["state"] == "accepted"


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


async def test_nested_local_mutation_is_reentrant_and_rolls_back_the_outer_transaction(local):
    store, user = local
    first, second = await task(store, user, "one"), await task(store, user, "two")

    @reminder_budget_transaction
    async def nested(api):
        await api.create_reminder(first["task_id"], user, AT)
        await api.create_reminder(second["task_id"], user, AT)

    with pytest.raises(ProactiveBudgetExceeded):
        await asyncio.wait_for(nested(store), timeout=1)
    assert not rows(containers(store)["reminders"])
    assert not store._proactive_state.reservations


@pytest.mark.parametrize("method", ["schedule", "later", "activation"])
async def test_memory_store_maps_budget_rpc_errors_without_provider_content(method):
    api = MemoryStore()
    query = SimpleNamespace(
        execute=AsyncMock(side_effect=RuntimeError("proactive_budget_exhausted private-key"))
    )
    api.db = SimpleNamespace(rpc=Mock(return_value=query))
    with pytest.raises(ProactiveBudgetExceeded, match="shared daily message budget") as error:
        if method == "schedule":
            await schedule(api, "owner", "task")
        elif method == "later":
            await api.apply_later_command(
                user_id="owner",
                idempotency_key="later",
                payload_hash="later",
                reminder_id="reminder",
                expected_task_version=1,
                step=1,
                scheduled_at=AT,
                intended_local_date="2026-10-22",
                intended_local_time="13:00:00",
                timezone="UTC",
                quiet_hours_adjusted=False,
                task_due_date="2026-10-22",
            )
        else:
            await api.create_activation_test_command(
                user_id="owner",
                idempotency_key="test",
                payload_hash="test",
                title="Private test",
                retry=False,
                scheduled_time=AT,
                intended_local_date="2026-10-22",
                intended_local_time="13:00:00",
                intended_timezone="UTC",
            )
    assert "private-key" not in str(error.value)


@pytest.mark.parametrize("action", ["cancel", "ack", "resolve"])
async def test_only_unsent_cancellation_or_ack_releases_capacity(local, action):
    store, user = local
    row = await task(store, user)
    reminder = await store.create_reminder(row["task_id"], user, AT)
    if action == "cancel":
        await store.cancel_reminder_command(
            user_id=user,
            idempotency_key="cancel",
            payload_hash="cancel",
            reminder_id=reminder["reminder_id"],
        )
    elif action == "ack":
        await store.acknowledge_reminders_for_task(row["task_id"], user)
    else:
        await store.resolve_task_command(
            user_id=user,
            idempotency_key="done",
            payload_hash="done",
            task_id=row["task_id"],
            outcome="completed",
            expected_version=row["version"],
            acted_reminder_id=None,
        )
    assert (
        store._proactive_state.reservations[user, f"reminder:{reminder['reminder_id']}"]["state"]
        == "cancelled"
    )
    next_task = await task(store, user, "next")
    assert await store.create_reminder(next_task["task_id"], user, AT)


async def test_cancellation_rolls_back_outer_local_transaction_and_releases_lock(local):
    store, user = local
    row = await task(store, user)

    @reminder_budget_transaction
    async def interrupted(api):
        await api.create_reminder(row["task_id"], user, AT)
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await interrupted(store)
    assert not rows(containers(store)["reminders"])
    assert not store._proactive_state.reservations
    assert await asyncio.wait_for(store.create_reminder(row["task_id"], user, AT), timeout=1)


async def test_explicit_cutover_backfill_preserves_accepted_and_attempted_evidence():
    from src.memory.proactive import LocalProactiveState

    state = LocalProactiveState()
    user = {"user_id": "owner", "timezone": "UTC", "daily_message_budget": 1}
    reminders = [
        {
            "reminder_id": "accepted",
            "user_id": "owner",
            "status": "pending",
            "scheduled_time": AT,
            "telegram_message_id": 44,
        },
        {"reminder_id": "unknown", "user_id": "owner", "status": "cancelled", "scheduled_time": AT},
    ]
    occurrences = {"unknown": {"occurrence_id": "attempted", "first_claimed_at": AT}}
    await state.backfill_reminders([user], reminders, occurrences)
    assert state.reservations["owner", "reminder:accepted"]["state"] == "accepted"
    assert state.reservations["owner", "reminder:unknown"]["state"] == "uncertain"
    assert state.reservations["owner", "reminder:unknown"]["legacy_debt"]
    assert not await state.release("owner", "reminder:accepted")
    assert not await state.release("owner", "reminder:unknown")
    assert (await state.reserve(user, "new", "reminder", AT))["status"] == "budget_exhausted"


async def test_memory_store_direct_insert_maps_budget_refusal():
    api = MemoryStore()
    task_query = Mock()
    for method in ["select", "eq", "maybe_single"]:
        getattr(task_query, method).return_value = task_query
    task_query.execute = AsyncMock(return_value=SimpleNamespace(data={"task_id": "task"}))
    reminder_query = Mock()
    reminder_query.insert.return_value = reminder_query
    reminder_query.execute = AsyncMock(
        side_effect=RuntimeError("proactive_budget_exhausted private-data")
    )
    api.db = SimpleNamespace(table=Mock(side_effect=[task_query, reminder_query]))
    with pytest.raises(ProactiveBudgetExceeded) as error:
        await api.create_reminder("task", "owner", AT)
    assert "private-data" not in str(error.value)
    reminder_query.insert.assert_called_once()


async def test_memory_store_immutable_time_refused_before_update_and_filters_owner():
    api = MemoryStore()
    query = Mock()
    for method in ["select", "eq", "maybe_single"]:
        getattr(query, method).return_value = query
    query.execute = AsyncMock(return_value=SimpleNamespace(data={"scheduled_time": AT}))
    api.db = SimpleNamespace(table=Mock(return_value=query))
    with pytest.raises(ValueError, match="reschedule"):
        await api.update_reminder("reminder", {"scheduled_time": TOMORROW}, "owner")
    query.eq.assert_any_call("user_id", "owner")
    query.eq.assert_any_call("reminder_id", "reminder")
    query.update.assert_not_called()


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


async def test_create_task_tool_keeps_task_and_explicitly_reports_no_reminder(local, monkeypatch):
    from src.tools.toolsets import create_task

    store, user = local
    ctx = await tool_context(store, user, monkeypatch)
    await sent_reminder(store, user)
    before_reminders = copy.deepcopy(containers(store)["reminders"])
    result = await create_task(ctx, "Read fictional book", reminder_time="in 90 minutes")
    assert result == (
        "Created task 'Read fictional book'. No Reminder scheduled: daily message budget is full."
    )
    assert any(row["title"] == "Read fictional book" for row in rows(containers(store)["tasks"]))
    assert containers(store)["reminders"] == before_reminders
    assert not ctx.deps.scheduler.scheduled


@pytest.mark.parametrize("tool_name", ["schedule_reminder", "apply_later"])
async def test_reminder_tools_report_budget_and_preserve_current_state(
    local, monkeypatch, tool_name
):
    from src.tools import toolsets

    store, user = local
    ctx = await tool_context(store, user, monkeypatch)
    row, reminder = await sent_reminder(store, user)
    before = copy.deepcopy(containers(store))
    if tool_name == "schedule_reminder":
        result = await toolsets.schedule_reminder(ctx, row["task_id"], "in 90 minutes")
        assert result == "Daily message budget is full. No Reminder was changed or scheduled."
    else:
        result = await toolsets.apply_later(ctx, reminder["reminder_id"])
        assert result == "Daily message budget is full. The current Reminder was not changed."
    assert containers(store) == before
    assert not ctx.deps.scheduler.scheduled


async def test_later_callback_reports_budget_instead_of_already_handled(local, monkeypatch):
    from src.bot.reminder_actions import ReminderActions

    store, user = local
    ctx = await tool_context(store, user, monkeypatch)
    _, reminder = await sent_reminder(store, user)
    before = copy.deepcopy(containers(store))
    actions = ReminderActions(ctx.deps.channel, store, ctx.deps.scheduler)
    await actions.handle_callback(19001, 701, f"later:{reminder['reminder_id']}")
    assert [message["text"] for message in ctx.deps.channel.sent] == [
        "Daily message budget is full. Your current Reminder was not changed."
    ]
    assert containers(store) == before
    assert not ctx.deps.scheduler.scheduled


@pytest.mark.parametrize("operation", ["schedule", "reschedule", "later"])
async def test_dashboard_budget_refusal_returns_409_and_preserves_state(
    local, monkeypatch, operation
):
    import httpx
    from fastapi import FastAPI

    from src.api.dependencies import get_activated_user
    from src.api.reminders import router

    store, user = local
    ctx = await tool_context(store, user, monkeypatch)
    row, reminder = await sent_reminder(store, user)
    if operation == "schedule":
        target = await task(store, user, "Second task")
        path = f"/api/tasks/{target['task_id']}/reminders"
    else:
        path = f"/api/reminders/{reminder['reminder_id']}/{operation}"
    payload = (
        {"expected_task_version": row["version"]}
        if operation == "later"
        else {"scheduled_at": "2026-10-22T14:00:00+00:00", "timezone": "UTC"}
    )
    before = copy.deepcopy(containers(store))
    app = FastAPI()
    app.state.store = store
    app.include_router(router)
    app.dependency_overrides[get_activated_user] = lambda: ctx.deps.user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(path, json=payload, headers={"Idempotency-Key": "budget-api"})
    assert response.status_code == 409
    assert response.json() == {"detail": "The shared daily message budget is full"}
    assert containers(store) == before
