"""Regression tests for the duplicate-task / duplicate-reminder bug.

Root cause: Gemini issued parallel create_task tool calls in a single agent turn,
producing two task rows and two reminder rows. Both reminders fired, producing two
"Good time?" messages and two "done" acknowledgements.

Fixes applied:
  - create_task is now idempotent: same (user, title, date) returns the existing row.
  - ScheduleReminderTool enforces at-most-one pending reminder per task.
"""

from datetime import timedelta

import pytest

from src.commands.base import CommandContext
from src.scheduler.outbox import SchedulerOutboxWorker
from src.tools.reminders import ScheduleReminderTool
from src.utils import utc_now
from tests.fakes import FakeScheduler, FakeStore


@pytest.fixture()
def store():
    return FakeStore()


@pytest.fixture()
def scheduler():
    return FakeScheduler()


async def _make_user_and_task(store: FakeStore) -> tuple[dict, dict]:
    user = await store.create_user(chat_id=1234)
    user["onboarding_complete"] = True
    user["timezone"] = "UTC"
    task = await store.create_task(
        user_id=user["user_id"],
        title="Go for a walk",
        category="health",
    )
    return user, task


async def test_schedule_reminder_tool_idempotent(store, scheduler):
    """Calling ScheduleReminderTool.run() twice for the same task should leave
    exactly ONE pending reminder in the store."""
    user, task = await _make_user_and_task(store)
    tool = ScheduleReminderTool(store, scheduler)

    send_time_str = (utc_now() + timedelta(minutes=10)).strftime("%H:%M")

    # First call — simulates create_task(reminder_time=...) internally scheduling
    await tool.run(
        context=CommandContext(user["user_id"], "telegram", "schedule-replay-1"),
        task=task,
        resolved_time=send_time_str,
        timezone="UTC",
    )

    # Second call — simulates the LLM also calling schedule_reminder explicitly
    await tool.run(
        context=CommandContext(user["user_id"], "telegram", "schedule-replay-1"),
        task=task,
        resolved_time=send_time_str,
        timezone="UTC",
    )

    pending = [r for r in store.reminders if r["status"] == "pending"]
    assert len(pending) == 1, (
        f"Expected 1 pending reminder, got {len(pending)}. "
        "Duplicate reminder creation bug has regressed."
    )
    assert len(store.scheduler_outbox) == 1
    assert scheduler.scheduled == []


async def test_schedule_reminder_cancels_previous_before_rescheduling(store, scheduler):
    """When a reminder is rescheduled, the old APScheduler job is cancelled."""
    user, task = await _make_user_and_task(store)
    tool = ScheduleReminderTool(store, scheduler)

    first_time = (utc_now() + timedelta(minutes=10)).strftime("%H:%M")
    second_time = (utc_now() + timedelta(minutes=30)).strftime("%H:%M")

    await tool.run(
        context=CommandContext(user["user_id"], "telegram", "schedule-first"),
        task=task,
        resolved_time=first_time,
        timezone="UTC",
    )

    first_reminder_id = store.reminders[0]["reminder_id"]

    await tool.run(
        context=CommandContext(user["user_id"], "telegram", "schedule-second"),
        task=task,
        resolved_time=second_time,
        timezone="UTC",
    )

    worker = SchedulerOutboxWorker(store, scheduler)
    assert await worker.drain_once() == 3
    assert first_reminder_id in scheduler.cancelled

    # Only one pending reminder remains
    pending = [r for r in store.reminders if r["status"] == "pending"]
    assert len(pending) == 1


async def test_create_task_idempotent(store):
    """Calling create_task twice with the same title on the same day returns the
    same task — no duplicate row is created. Guards against the LLM issuing two
    parallel create_task tool calls in one agent turn."""
    user = await store.create_user(chat_id=5555)
    user["timezone"] = "UTC"

    task1 = await store.create_task(
        user_id=user["user_id"], title="Go for a walk", timezone="UTC"
    )
    task2 = await store.create_task(
        user_id=user["user_id"], title="Go for a walk", timezone="UTC"
    )

    assert task1["task_id"] == task2["task_id"], (
        "Same title on same day must return the same task row."
    )
    assert len([t for t in store.tasks if t["title"] == "Go for a walk"]) == 1, (
        "Only one task row should exist."
    )


async def test_create_task_after_done_creates_new(store):
    """A completed task does NOT block creating a fresh same-titled task —
    the dedup only applies to non-done/non-skipped tasks."""
    user = await store.create_user(chat_id=6666)
    user["timezone"] = "UTC"

    task1 = await store.create_task(
        user_id=user["user_id"], title="Go for a walk", timezone="UTC"
    )
    await store.update_task_status(task1["task_id"], "completed", user["user_id"])

    task2 = await store.create_task(
        user_id=user["user_id"], title="Go for a walk", timezone="UTC"
    )
    assert task1["task_id"] != task2["task_id"], (
        "A new task should be created after the previous one is done."
    )
