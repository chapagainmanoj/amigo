"""Canonical Later policy and cross-surface command tests."""

from datetime import datetime

import httpx
import pytest
from fastapi import FastAPI

from src.api.reminders import router
from src.auth import get_authenticated_user_id
from src.bot.reminder_actions import ReminderActions
from src.commands.base import CommandContext, StaleVersionError
from src.commands.later import ApplyLaterCommand, LaterPolicy
from src.memory.memory_store import InMemoryStore
from src.scheduler.outbox import SchedulerOutboxWorker
from src.utils import Clock
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


class MutableClock(Clock):
    def __init__(self, current: datetime):
        self.current = current

    def utc_now(self) -> datetime:
        return self.current


def _reminders(store) -> list[dict]:
    return store.reminders if isinstance(store, FakeStore) else list(store._reminders.values())


def _outbox(store) -> dict[str, dict]:
    return store.scheduler_outbox if isinstance(store, FakeStore) else store._scheduler_outbox


async def _seed(store, *, timezone="UTC", wake="07:30", sleep="23:00"):
    user = await store.create_user(123)
    await store.update_user(
        user["user_id"],
        {"timezone": timezone, "wake_time": wake, "sleep_time": sleep},
    )
    task = await store.create_task(user["user_id"], "Finish report", timezone=timezone)
    reminder = await store.create_reminder(
        task["task_id"],
        user["user_id"],
        "2026-08-31T10:00:00+00:00",
    )
    await store.update_reminder(reminder["reminder_id"], {"status": "sent"}, user["user_id"])
    return user, task, reminder


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_later_runs_60_then_30_then_next_planning_day(store_factory):
    store = store_factory()
    user, task, reminder = await _seed(store)
    clock = MutableClock(datetime(2026, 8, 31, 10, 0))
    command = ApplyLaterCommand(store, LaterPolicy(clock))

    first = await command.run(
        CommandContext(user["user_id"], "telegram", "later-1"),
        reminder_id=reminder["reminder_id"],
        expected_task_version=1,
    )
    assert first["later_step"] == 1
    assert first["intended_local_time"] == "11:00:00"
    assert first["acknowledged_reminder"]["status"] == "acknowledged"
    assert first["reminder"]["reminder_id"] != reminder["reminder_id"]

    clock.current = datetime(2026, 8, 31, 11, 0)
    await store.update_reminder(
        first["reminder"]["reminder_id"],
        {"status": "sent"},
        user["user_id"],
    )
    second = await command.run(
        CommandContext(user["user_id"], "dashboard", "later-2"),
        reminder_id=first["reminder"]["reminder_id"],
        expected_task_version=2,
    )
    assert second["later_step"] == 2
    assert second["intended_local_time"] == "11:30:00"

    clock.current = datetime(2026, 8, 31, 11, 30)
    await store.update_reminder(
        second["reminder"]["reminder_id"],
        {"status": "sent"},
        user["user_id"],
    )
    third = await command.run(
        CommandContext(user["user_id"], "telegram", "later-3"),
        reminder_id=second["reminder"]["reminder_id"],
        expected_task_version=3,
    )

    assert third["later_step"] == 3
    assert third["intended_local_date"] == "2026-09-01"
    assert third["intended_local_time"] == "07:30:00"
    assert third["task"]["due_date"] == "2026-09-01"
    assert third["task"]["status"] == "pending"
    assert third["task"]["deferred_count"] == 3
    assert len([item for item in _reminders(store) if item["status"] == "pending"]) == 1
    assert len(_outbox(store)) == 6


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_later_moves_automatic_delay_past_quiet_hours(store_factory):
    store = store_factory()
    user, _, reminder = await _seed(store)
    command = ApplyLaterCommand(
        store,
        LaterPolicy(MutableClock(datetime(2026, 8, 31, 22, 30))),
    )

    result = await command.run(
        CommandContext(user["user_id"], "telegram", "later-quiet"),
        reminder_id=reminder["reminder_id"],
    )

    assert result["quiet_hours_adjusted"] is True
    assert result["intended_local_date"] == "2026-09-01"
    assert result["intended_local_time"] == "07:30:00"
    assert result["intended_timezone"] == "UTC"


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_later_replay_stale_and_wrong_owner_are_safe(store_factory):
    store = store_factory()
    owner, task, reminder = await _seed(store)
    intruder = await store.create_user(456)
    command = ApplyLaterCommand(
        store,
        LaterPolicy(MutableClock(datetime(2026, 8, 31, 10, 0))),
    )
    context = CommandContext(owner["user_id"], "dashboard", "later-replay")

    first = await command.run(
        context,
        reminder_id=reminder["reminder_id"],
        expected_task_version=1,
    )
    replay = await command.run(
        context,
        reminder_id=reminder["reminder_id"],
        expected_task_version=1,
    )
    assert replay == first
    assert len(_reminders(store)) == 2
    assert len(_outbox(store)) == 2

    with pytest.raises(ValueError, match="already|active"):
        await command.run(
            CommandContext(owner["user_id"], "dashboard", "later-repeat"),
            reminder_id=reminder["reminder_id"],
        )
    with pytest.raises(ValueError, match="Reminder not found"):
        await command.run(
            CommandContext(intruder["user_id"], "dashboard", "later-intruder"),
            reminder_id=reminder["reminder_id"],
        )
    with pytest.raises(StaleVersionError):
        await command.run(
            CommandContext(owner["user_id"], "dashboard", "later-stale"),
            reminder_id=first["reminder"]["reminder_id"],
            expected_task_version=1,
        )
    assert task["status"] == "pending"


class FailingSchedule(FakeScheduler):
    def schedule_reminder(self, user_id, reminder_id, send_time, chat_id, task_title):
        raise RuntimeError("scheduler unavailable")


async def test_later_intent_survives_scheduler_outage():
    store = FakeStore()
    user, _, reminder = await _seed(store)
    result = await ApplyLaterCommand(
        store,
        LaterPolicy(MutableClock(datetime(2026, 8, 31, 10, 0))),
    ).run(
        CommandContext(user["user_id"], "telegram", "later-outage"),
        reminder_id=reminder["reminder_id"],
    )

    worker = SchedulerOutboxWorker(store, FailingSchedule())
    assert await worker.drain_once() == 1
    schedule_effect = _outbox(store)[f"schedule:{result['reminder']['reminder_id']}"]
    assert schedule_effect["status"] == "pending"
    assert result["effect_state"] == "queued"


async def test_dashboard_and_telegram_adapters_apply_shared_later_command():
    store = FakeStore()
    user, _, dashboard_reminder = await _seed(store)
    await store.update_user(user["user_id"], {"supabase_auth_id": "auth-user"})

    app = FastAPI()
    app.state.store = store
    app.include_router(router)
    app.dependency_overrides[get_authenticated_user_id] = lambda: "auth-user"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"/api/reminders/{dashboard_reminder['reminder_id']}/later",
            headers={"Idempotency-Key": "dashboard-later"},
            json={"expected_task_version": 1},
        )

    telegram_task = await store.create_task(user["user_id"], "Telegram Later")
    telegram_reminder = await store.create_reminder(
        telegram_task["task_id"],
        user["user_id"],
        "2099-01-01T00:00:00+00:00",
    )
    await store.update_reminder(
        telegram_reminder["reminder_id"],
        {"status": "sent"},
        user["user_id"],
    )
    channel = FakeChannel()
    await ReminderActions(channel, store, FakeScheduler()).handle_callback(
        123,
        1,
        f"later:{telegram_reminder['reminder_id']}",
    )

    assert response.status_code == 202
    assert response.json()["later_step"] == 1
    assert "Next reminder:" in channel.last_text
    assert dashboard_reminder["status"] == "acknowledged"
    assert telegram_reminder["status"] == "acknowledged"
