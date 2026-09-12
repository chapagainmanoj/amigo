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
    occurrence = store.reminder_occurrences[reminder["reminder_id"]]
    attempt = next(iter(store.reminder_delivery_attempts.values()))
    assert occurrence["confirmed_at"] is not None
    assert occurrence["first_claimed_at"] is not None
    assert occurrence["provider_accepted_at"] is not None
    assert attempt["result"] == "accepted"
    assert attempt["retry_decision"] == "do_not_retry"
    assert attempt["provider_latency_ms"] is not None


async def test_ambiguous_send_failure_is_terminal_without_false_acceptance():
    class FailingChannel(FakeChannel):
        async def send_message(self, chat_id, text, *, buttons=None):
            raise TimeoutError("injected provider failure")

    store = FakeStore()
    _, _, reminder = await _create_user_task_reminder(store)
    scheduler = ReminderScheduler(channel=FailingChannel(), store=store)

    await scheduler._send_reminder(
        reminder["user_id"], 123, reminder["reminder_id"], "finish slides"
    )

    occurrence = store.reminder_occurrences[reminder["reminder_id"]]
    attempt = next(iter(store.reminder_delivery_attempts.values()))
    assert reminder["status"] == "failed"
    assert occurrence["first_claimed_at"] is not None
    assert occurrence["provider_accepted_at"] is None
    assert occurrence["terminal_at"] is not None
    assert attempt["result"] == "timeout"
    assert attempt["normalized_cause"] == "TimeoutError"
    assert attempt["retry_decision"] == "do_not_retry"


async def test_send_reminder_cannot_claim_resolved_tasks():
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
        assert reminder["status"] == "pending"


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
    assert scheduler.scheduler.get_job(f"recovery:{missed['user_id']}") is not None
    assert scheduler.scheduler.get_job(f"{old['user_id']}:{old['reminder_id']}") is None
    assert old["status"] == "missed"


async def test_reconciliation_repairs_time_and_removes_inverse_drift():
    now = datetime(2026, 6, 14, 10, 0)
    store = FakeStore()
    user, task, reminder = await _create_user_task_reminder(
        store, scheduled_time=now + timedelta(hours=1)
    )
    scheduler = ReminderScheduler(FakeChannel(), store, FixedClock(now))
    scheduler.schedule_reminder(
        user["user_id"], reminder["reminder_id"], now + timedelta(hours=5), 123, "wrong"
    )
    scheduler.schedule_reminder(
        "ghost-user", "ghost-reminder", now + timedelta(hours=2), 999, "ghost"
    )

    report = await scheduler.reconcile()

    repaired = scheduler.scheduler.get_job(f"{user['user_id']}:{reminder['reminder_id']}")
    assert repaired.trigger.run_date.replace(tzinfo=None) == now + timedelta(hours=1)
    assert scheduler.scheduler.get_job("ghost-user:ghost-reminder") is None
    assert report == {
        "scheduled": 1,
        "recovered": 0,
        "missed": 0,
        "failed": 0,
        "cancelled": 1,
        "missing_jobs": 0,
        "wrong_time_jobs": 1,
    }
    assert store.scheduler_runtime["wrong_time_jobs"] == 1
    assert store.scheduler_runtime["inverse_drift_jobs"] == 1

    task["user_id"] = "wrong-owner"
    await scheduler.reconcile()
    assert scheduler.scheduler.get_job(f"{user['user_id']}:{reminder['reminder_id']}") is None


async def test_interrupted_send_recovers_and_delayed_reminders_emit_one_summary():
    now = datetime(2026, 6, 14, 10, 0)
    store = FakeStore()
    channel = FakeChannel()
    user, task, first = await _create_user_task_reminder(
        store, scheduled_time=now - timedelta(minutes=2)
    )
    second = await store.create_reminder(
        task["task_id"], user["user_id"], (now - timedelta(minutes=1)).isoformat()
    )
    first["status"] = "sending"
    scheduler = ReminderScheduler(channel, store, FixedClock(now))

    report = await scheduler.reconcile()
    job = scheduler.scheduler.get_job(f"recovery:{user['user_id']}")
    assert report["recovered"] == 1
    assert job is not None

    await scheduler._send_recovery_summary(**job.kwargs)
    await scheduler._send_recovery_summary(**job.kwargs)

    assert len(channel.sent) == 1
    assert first["status"] == "sent"
    assert second["status"] == "sent"
    assert task["status"] == "pending"


async def test_reconciliation_does_not_retry_an_unfinished_delivery_attempt():
    now = datetime(2026, 6, 14, 10, 0)
    store = FakeStore()
    user, _, reminder = await _create_user_task_reminder(
        store, scheduled_time=now - timedelta(minutes=2)
    )
    claimed = await store.claim_reminder_for_send(
        reminder["reminder_id"], user["user_id"], "interrupted-attempt"
    )
    scheduler = ReminderScheduler(FakeChannel(), store, FixedClock(now))

    report = await scheduler.reconcile()

    attempt = store.reminder_delivery_attempts[claimed["attempt"]["attempt_id"]]
    assert report["failed"] == 1
    assert reminder["status"] == "failed"
    assert attempt["result"] == "error"
    assert attempt["normalized_cause"] == "interrupted_delivery_unknown"
    assert attempt["retry_decision"] == "do_not_retry"
    assert scheduler.scheduler.get_job(f"recovery:{user['user_id']}") is None
