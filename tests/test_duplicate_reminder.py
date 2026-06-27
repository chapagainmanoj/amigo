"""Regression test — duplicate reminder creation.

Reproduces the bug where the LLM calls both create_task(reminder_time=...) AND
schedule_reminder(...) in the same turn, resulting in two DB reminder rows, two
"Good time?" messages, and two "done" acknowledgements.

The fix: ScheduleReminderTool.run() cancels existing pending reminders for the
task before inserting a new one, making it idempotent.
"""

from datetime import timedelta

import pytest

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
        user_id=user["user_id"],
        task=task,
        resolved_time=send_time_str,
        timezone="UTC",
        chat_id=1234,
    )

    # Second call — simulates the LLM also calling schedule_reminder explicitly
    await tool.run(
        user_id=user["user_id"],
        task=task,
        resolved_time=send_time_str,
        timezone="UTC",
        chat_id=1234,
    )

    pending = [r for r in store.reminders if r["status"] == "pending"]
    assert len(pending) == 1, (
        f"Expected 1 pending reminder, got {len(pending)}. "
        "Duplicate reminder creation bug has regressed."
    )


async def test_schedule_reminder_cancels_previous_before_rescheduling(store, scheduler):
    """When a reminder is rescheduled, the old APScheduler job is cancelled."""
    user, task = await _make_user_and_task(store)
    tool = ScheduleReminderTool(store, scheduler)

    first_time = (utc_now() + timedelta(minutes=10)).strftime("%H:%M")
    second_time = (utc_now() + timedelta(minutes=30)).strftime("%H:%M")

    await tool.run(
        user_id=user["user_id"],
        task=task,
        resolved_time=first_time,
        timezone="UTC",
        chat_id=1234,
    )

    first_reminder_id = store.reminders[0]["reminder_id"]

    await tool.run(
        user_id=user["user_id"],
        task=task,
        resolved_time=second_time,
        timezone="UTC",
        chat_id=1234,
    )

    # The first reminder_id must have been cancelled in the scheduler
    assert first_reminder_id in scheduler.cancelled, (
        "Old reminder job should be cancelled when rescheduling."
    )

    # Only one pending reminder remains
    pending = [r for r in store.reminders if r["status"] == "pending"]
    assert len(pending) == 1
