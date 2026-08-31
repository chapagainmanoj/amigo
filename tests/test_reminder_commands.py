"""Shared Reminder commands and durable scheduler-outbox coverage."""

from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from src.api.reminders import router
from src.auth import get_authenticated_user_id
from src.commands.base import CommandContext, IdempotencyConflictError
from src.commands.reminders import (
    CancelReminderCommand,
    ReminderScheduleInput,
    RescheduleReminderCommand,
    ScheduleReminderCommand,
)
from src.memory.memory_store import InMemoryStore
from src.scheduler.outbox import SchedulerOutboxWorker
from tests.fakes import FakeScheduler, FakeStore

SCHEDULE = ReminderScheduleInput(
    scheduled_at=datetime(2099, 1, 2, 12, 30, tzinfo=UTC),
    timezone="America/New_York",
)
LATER_SCHEDULE = ReminderScheduleInput(
    scheduled_at=datetime(2099, 1, 2, 14, 0, tzinfo=UTC),
    timezone="America/New_York",
)


def _active_reminders(store) -> list[dict]:
    reminders = store.reminders if isinstance(store, FakeStore) else store._reminders.values()
    return [item for item in reminders if item["status"] in {"pending", "sending", "sent"}]


def _outbox(store) -> dict[str, dict]:
    return store.scheduler_outbox if isinstance(store, FakeStore) else store._scheduler_outbox


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_schedule_replay_is_atomic_and_returns_queued_result(store_factory):
    store = store_factory()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "Prepare report")
    context = CommandContext(user["user_id"], "telegram", "schedule-request-1")
    command = ScheduleReminderCommand(store)

    first = await command.run(context, task_id=task["task_id"], schedule=SCHEDULE)
    replay = await command.run(context, task_id=task["task_id"], schedule=SCHEDULE)

    assert replay == first
    assert first["effect_state"] == "queued"
    assert first["task_version"] == 2
    assert first["scheduled_time"] == "2099-01-02T12:30:00+00:00"
    assert first["reminder"]["intended_local_date"] == "2099-01-02"
    assert first["reminder"]["intended_local_time"] == "07:30:00"
    assert len(_active_reminders(store)) == 1
    assert len(_outbox(store)) == 1


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_reschedule_cancels_old_row_and_creates_replacement(store_factory):
    store = store_factory()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "Prepare report")
    first = await ScheduleReminderCommand(store).run(
        CommandContext(user["user_id"], "dashboard", "schedule-request-2"),
        task_id=task["task_id"],
        schedule=SCHEDULE,
    )

    result = await RescheduleReminderCommand(store).run(
        CommandContext(user["user_id"], "dashboard", "reschedule-request-1"),
        reminder_id=first["reminder"]["reminder_id"],
        schedule=LATER_SCHEDULE,
    )

    assert first["reminder"]["reminder_id"] != result["reminder"]["reminder_id"]
    assert len(_active_reminders(store)) == 1
    assert _active_reminders(store)[0]["reminder_id"] == result["reminder"]["reminder_id"]
    assert len(_outbox(store)) == 3


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_cancel_is_owned_idempotent_and_queues_stable_effect(store_factory):
    store = store_factory()
    owner = await store.create_user(123)
    intruder = await store.create_user(456)
    task = await store.create_task(owner["user_id"], "Prepare report")
    scheduled = await ScheduleReminderCommand(store).run(
        CommandContext(owner["user_id"], "telegram", "schedule-request-3"),
        task_id=task["task_id"],
        schedule=SCHEDULE,
    )
    reminder_id = scheduled["reminder"]["reminder_id"]

    with pytest.raises(ValueError, match="Reminder not found"):
        await CancelReminderCommand(store).run(
            CommandContext(intruder["user_id"], "dashboard", "cancel-intruder"),
            reminder_id=reminder_id,
        )

    context = CommandContext(owner["user_id"], "dashboard", "cancel-owner")
    first = await CancelReminderCommand(store).run(context, reminder_id=reminder_id)
    replay = await CancelReminderCommand(store).run(context, reminder_id=reminder_id)

    assert replay == first
    assert first["reminder"]["status"] == "cancelled"
    assert first["effect_state"] == "queued"
    assert len(_active_reminders(store)) == 0
    assert len(_outbox(store)) == 2


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_reminder_idempotency_conflict_does_not_mutate(store_factory):
    store = store_factory()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "Prepare report")
    context = CommandContext(user["user_id"], "telegram", "schedule-conflict")
    command = ScheduleReminderCommand(store)
    await command.run(context, task_id=task["task_id"], schedule=SCHEDULE)

    with pytest.raises(IdempotencyConflictError):
        await command.run(context, task_id=task["task_id"], schedule=LATER_SCHEDULE)

    assert len(_active_reminders(store)) == 1
    assert len(_outbox(store)) == 1


class _FailOnceScheduler(FakeScheduler):
    def __init__(self):
        super().__init__()
        self.fail_next = True

    def schedule_reminder(self, user_id, reminder_id, send_time, chat_id, task_title):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("temporary scheduler failure")
        return super().schedule_reminder(user_id, reminder_id, send_time, chat_id, task_title)


async def test_scheduler_failure_keeps_effect_for_safe_replay():
    store = FakeStore()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "Prepare report")
    result = await ScheduleReminderCommand(store).run(
        CommandContext(user["user_id"], "telegram", "schedule-failure"),
        task_id=task["task_id"],
        schedule=SCHEDULE,
    )
    scheduler = _FailOnceScheduler()
    worker = SchedulerOutboxWorker(store, scheduler)

    assert await worker.drain_once() == 0
    effect = _outbox(store)[f"schedule:{result['reminder']['reminder_id']}"]
    assert effect["status"] == "pending"
    assert await worker.drain_once() == 1
    assert effect["status"] == "completed"
    assert len(scheduler.scheduled) == 1


async def test_dashboard_reminder_adapters_return_202_and_derive_actor():
    store = FakeStore()
    user = await store.create_user(123)
    await store.update_user(user["user_id"], {"supabase_auth_id": "auth-user"})
    task = await store.create_task(user["user_id"], "Dashboard Task")
    app = FastAPI()
    app.state.store = store
    app.include_router(router)
    app.dependency_overrides[get_authenticated_user_id] = lambda: "auth-user"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        scheduled = await client.post(
            f"/api/tasks/{task['task_id']}/reminders",
            headers={"Idempotency-Key": "dashboard-schedule"},
            json={"scheduled_at": "2099-01-02T12:30:00Z", "timezone": "UTC"},
        )
        reminder_id = scheduled.json()["reminder"]["reminder_id"]
        rescheduled = await client.post(
            f"/api/reminders/{reminder_id}/reschedule",
            headers={"Idempotency-Key": "dashboard-reschedule"},
            json={"scheduled_at": "2099-01-02T14:00:00Z", "timezone": "UTC"},
        )
        replacement_id = rescheduled.json()["reminder"]["reminder_id"]
        cancelled = await client.delete(
            f"/api/reminders/{replacement_id}",
            headers={"Idempotency-Key": "dashboard-cancel"},
        )
        supplied_identity = await client.post(
            f"/api/tasks/{task['task_id']}/reminders",
            headers={"Idempotency-Key": "dashboard-identity"},
            json={
                "scheduled_at": "2099-01-02T15:00:00Z",
                "timezone": "UTC",
                "user_id": "attacker-selected",
            },
        )
        invalid_time = await client.post(
            f"/api/tasks/{task['task_id']}/reminders",
            headers={"Idempotency-Key": "dashboard-invalid-time"},
            json={"scheduled_at": "2020-01-02T15:00:00Z", "timezone": "UTC"},
        )

    assert scheduled.status_code == 202
    assert rescheduled.status_code == 202
    assert cancelled.status_code == 202
    assert supplied_identity.status_code == 422
    assert invalid_time.status_code == 422
    assert scheduled.json()["reminder"]["user_id"] == user["user_id"]
