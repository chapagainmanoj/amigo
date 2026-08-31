"""ReminderScheduler job management and delivery tests."""

from datetime import datetime, timedelta

from src.scheduler.reminders import ReminderScheduler
from tests.fakes import FakeChannel, FakeStore


class FixedClock:
    def __init__(self, now: datetime):
        self._now = now

    def utc_now(self) -> datetime:
        return self._now


async def _create_user_task_reminder(
    store: FakeStore,
    *,
    chat_id: int = 123,
    task_title: str = "finish slides",
    scheduled_time: datetime | None = None,
) -> tuple[dict, dict, dict]:
    user = await store.create_user(chat_id)
    task = await store.create_task(user["user_id"], task_title)
    reminder = await store.create_reminder(
        task_id=task["task_id"],
        user_id=user["user_id"],
        scheduled_time=(scheduled_time or datetime(2099, 1, 1, 12, 0, 0)).isoformat(),
    )
    return user, task, reminder


def test_schedule_reminder_registers_job_with_stable_id_and_kwargs():
    store = FakeStore()
    channel = FakeChannel()
    scheduler = ReminderScheduler(channel=channel, store=store)
    send_time = datetime(2099, 1, 1, 12, 0, 0)

    scheduler.schedule_reminder(
        user_id="user-1",
        reminder_id="reminder-1",
        send_time=send_time,
        chat_id=123,
        task_title="finish slides",
    )

    job = scheduler.scheduler.get_job("user-1:reminder-1")
    assert job is not None
    assert job.kwargs == {
        "user_id": "user-1",
        "chat_id": 123,
        "reminder_id": "reminder-1",
        "task_title": "finish slides",
    }
    assert job.trigger.run_date.replace(tzinfo=None) == send_time


def test_schedule_reminder_replaces_existing_job_for_same_reminder():
    scheduler = ReminderScheduler(channel=FakeChannel(), store=FakeStore())

    scheduler.schedule_reminder("user-1", "reminder-1", datetime(2099, 1, 1, 12), 123, "old")
    scheduler.schedule_reminder("user-1", "reminder-1", datetime(2099, 1, 1, 13), 456, "new")

    jobs = scheduler.scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].kwargs["chat_id"] == 456
    assert jobs[0].kwargs["task_title"] == "new"


def test_cancel_reminder_removes_registered_job():
    scheduler = ReminderScheduler(channel=FakeChannel(), store=FakeStore())
    scheduler.schedule_reminder(
        user_id="user-1",
        reminder_id="reminder-1",
        send_time=datetime(2099, 1, 1, 12, 0, 0),
        chat_id=123,
        task_title="finish slides",
    )

    scheduler.cancel_reminder("user-1", "reminder-1")

    assert scheduler.scheduler.get_job("user-1:reminder-1") is None


async def test_send_reminder_sends_buttons_and_marks_sent():
    store = FakeStore()
    channel = FakeChannel()
    _, _, reminder = await _create_user_task_reminder(store)
    scheduler = ReminderScheduler(channel=channel, store=store)

    await scheduler._send_reminder(
        reminder["user_id"], 123, reminder["reminder_id"], "finish slides"
    )

    assert len(channel.sent) == 1
    assert channel.sent[0]["buttons"] is not None
    assert reminder["status"] == "sent"
    assert reminder["telegram_message_id"] == channel.sent[0]["message_id"]


async def test_send_reminder_skips_done_or_skipped_tasks():
    for status in ("completed", "skipped", "cancelled"):
        store = FakeStore()
        channel = FakeChannel()
        _, task, reminder = await _create_user_task_reminder(store)
        await store.update_task_status(task["task_id"], status, task["user_id"])
        scheduler = ReminderScheduler(channel=channel, store=store)

        await scheduler._send_reminder(
            reminder["user_id"], 123, reminder["reminder_id"], "finish slides"
        )

        assert channel.sent == []
        assert reminder["status"] == "acknowledged"


async def test_reload_pending_schedules_future_and_recently_missed_reminders():
    now = datetime(2026, 6, 14, 10, 0, 0)
    store = FakeStore()
    channel = FakeChannel()
    user, _, future = await _create_user_task_reminder(
        store,
        scheduled_time=now + timedelta(minutes=10),
    )
    _, _, missed = await _create_user_task_reminder(
        store,
        chat_id=456,
        scheduled_time=now - timedelta(minutes=5),
    )
    _, _, old = await _create_user_task_reminder(
        store,
        chat_id=789,
        scheduled_time=now - timedelta(minutes=30),
    )
    scheduler = ReminderScheduler(channel=channel, store=store, clock=FixedClock(now))

    await scheduler.reload_pending()

    assert scheduler.scheduler.get_job(f"{user['user_id']}:{future['reminder_id']}") is not None
    assert scheduler.scheduler.get_job(f"{missed['user_id']}:{missed['reminder_id']}") is not None
    assert scheduler.scheduler.get_job(f"{old['user_id']}:{old['reminder_id']}") is None
