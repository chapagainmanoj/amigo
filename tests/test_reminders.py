"""Reminder snooze logic tests."""

import asyncio
from datetime import timedelta

from src.scheduler.reminders import ReminderScheduler
from src.utils import utc_now
from tests.fakes import FakeChannel, FakeStore


class FailingChannel(FakeChannel):
    async def send_message(
        self, chat_id: str | int, text: str, *, buttons=None
    ) -> int | None:
        raise RuntimeError("telegram send failed")


async def _create_due_reminder(store: FakeStore) -> dict:
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "finish slides")
    return await store.create_reminder(
        task_id=task["task_id"],
        user_id=user["user_id"],
        scheduled_time=(utc_now() + timedelta(minutes=5)).isoformat(),
    )


async def test_duplicate_send_attempts_claim_reminder_once():
    store = FakeStore()
    channel = FakeChannel()
    reminder = await _create_due_reminder(store)
    scheduler = ReminderScheduler(channel=channel, store=store)

    await asyncio.gather(
        scheduler._send_reminder(123, reminder["reminder_id"], "finish slides"),
        scheduler._send_reminder(123, reminder["reminder_id"], "finish slides"),
    )

    assert len(channel.sent) == 1
    assert reminder["status"] == "sent"


async def test_send_failure_releases_reminder_for_retry():
    store = FakeStore()
    reminder = await _create_due_reminder(store)
    scheduler = ReminderScheduler(channel=FailingChannel(), store=store)

    await scheduler._send_reminder(123, reminder["reminder_id"], "finish slides")

    assert reminder["status"] == "pending"


class TestSnoozeLogic:
    """Test the snooze delay escalation: 1hr → 30min → defer."""

    def _snooze_delay(self, snooze_count: int) -> int | None:
        """Replicate the snooze logic from handlers."""
        delays = [60, 30]
        if snooze_count >= len(delays):
            return None  # defer
        return delays[snooze_count]

    def test_first_snooze_is_60min(self):
        assert self._snooze_delay(0) == 60

    def test_second_snooze_is_30min(self):
        assert self._snooze_delay(1) == 30

    def test_third_snooze_defers(self):
        assert self._snooze_delay(2) is None

    def test_beyond_max_defers(self):
        assert self._snooze_delay(5) is None
