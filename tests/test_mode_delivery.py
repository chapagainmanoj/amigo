"""Reminder addressing is resolved against the fresh participant at delivery time."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from src.channels.base import ConversationRef
from src.scheduler.reminders import ReminderScheduler
from src.utils import utc_now
from tests.fakes import FakeChannel, FakeStore


async def _reminder(store, chat_id=123):
    user = await store.create_user(chat_id)
    task = await store.create_task(user["user_id"], "Test task")
    reminder = await store.create_reminder(
        task["task_id"], user["user_id"], (utc_now() + timedelta(minutes=5)).isoformat(),
    )
    return user, reminder


def _stub_conversations(scheduler, channel_id="telegram", *, returns=None):
    """Replace the scheduler's per-channel conversation service with a stub."""
    service = type("ConversationService", (), {})()
    service.ensure = AsyncMock(return_value=returns)
    scheduler._mode_conversations[channel_id] = service
    return service


@pytest.mark.parametrize("recovery", [False, True])
async def test_delivery_resolves_daily_conversation_after_scheduling(recovery):
    store, channel = FakeStore(), FakeChannel(threads=True)
    user, reminder = await _reminder(store)
    scheduler = ReminderScheduler(channel, store)
    original = ConversationRef(channel.channel_id, {"chat_id": 123, "opaque": "old"})
    current = ConversationRef(channel.channel_id, {"chat_id": 123, "opaque": "current"})
    service = _stub_conversations(scheduler, returns=original)
    scheduler.schedule_reminder(user["user_id"], reminder["reminder_id"],
                                utc_now() + timedelta(minutes=5), 123, "Test task")
    service.ensure.return_value = current
    if recovery:
        await scheduler._send_recovery_summary(user["user_id"], 123, [reminder])
    else:
        await scheduler._send_reminder(user["user_id"], 123, reminder["reminder_id"], "Test task")
    assert channel.sent[0]["conversation"] == current
    service.ensure.assert_awaited_once()
    assert service.ensure.call_args.args[1] == "daily"
    assert "conversation" not in scheduler.scheduler.get_jobs()[0].kwargs


async def test_delivery_uses_fresh_linked_chat_instead_of_scheduled_chat(monkeypatch):
    store, channel = FakeStore(), FakeChannel()
    user, reminder = await _reminder(store)
    monkeypatch.setattr(store, "get_user_by_id", AsyncMock(return_value={
        **user, "telegram_chat_id": 456,
    }))
    scheduler = ReminderScheduler(channel, store)
    service = _stub_conversations(scheduler)
    await scheduler._send_reminder(user["user_id"], 123, reminder["reminder_id"], "Test task")
    assert channel.sent[0]["chat_id"] == 456
    assert service.ensure.call_args.kwargs == {"chat_id": 456}


async def test_different_primary_channel_is_not_sent_through_old_channel(monkeypatch):
    store, channel = FakeStore(), FakeChannel()
    user, reminder = await _reminder(store)
    monkeypatch.setattr(store, "get_user_by_id", AsyncMock(return_value={
        **user, "primary_channel": "unavailable-channel",
    }))
    scheduler = ReminderScheduler(channel, store)
    await scheduler._send_reminder(user["user_id"], 123, reminder["reminder_id"], "Test task")
    assert not channel.sent
    # Left for the primary channel's process: never claimed, so never marked failed.
    assert not store.reminder_delivery_attempts
    assert store.reminders[0]["status"] == "pending"


async def test_reconciliation_preserves_mode_maintenance_job():
    scheduler = ReminderScheduler(FakeChannel(), FakeStore())
    await scheduler.start_mode_maintenance(AsyncMock())
    await scheduler.reconcile()
    job = scheduler.scheduler.get_job("mode-conversation-maintenance")
    assert job is not None and job.max_instances == 1


async def test_relinked_participant_gets_fresh_daily_conversation_before_delivery():
    store, channel = FakeStore(), FakeChannel(threads=True)
    user, reminder = await _reminder(store)
    await store.save_mode_conversation(
        user["user_id"], "daily", channel.channel_id, {"chat_id": 123, "thread_id": 19},
    )
    await store.update_user(user["user_id"], {"telegram_chat_id": 456})
    scheduler = ReminderScheduler(channel, store)
    await scheduler._send_reminder(user["user_id"], 123, reminder["reminder_id"], "Test task")
    assert len(channel.sent) == 1
    assert channel.sent[0]["chat_id"] == 456
    assert channel.sent[0]["conversation"].endpoint["chat_id"] == 456
    current = await store.get_mode_conversation(user["user_id"], "daily", channel.channel_id)
    assert current["endpoint"]["chat_id"] == 456
    assert current["endpoint"] != {"chat_id": 123, "thread_id": 19}


async def _second_app_primary(store):
    """A Telegram participant who linked fake2 and made it their primary channel."""
    user, reminder = await _reminder(store, 124)
    store._identity_state.link(user["user_id"], "fake2", "ext-124")
    await store.set_primary_channel(user["user_id"], "fake2")
    return user, reminder


def _fake2_channel(store):
    """A second adapter resolves its own address from the Store's channel identities."""
    channel = FakeChannel(channel_id="fake2")

    async def recipient_for(user):
        return (await store.list_channel_identities(user["user_id"])).get("fake2")

    channel.recipient_for = recipient_for
    return channel


async def test_reminder_goes_only_to_the_primary_channel_and_records_its_proof():
    store = FakeStore()
    user, reminder = await _second_app_primary(store)
    telegram = ReminderScheduler(FakeChannel(), store)
    await telegram._send_reminder(user["user_id"], None, reminder["reminder_id"], "Test task")
    assert not telegram.channel.sent
    assert store.reminders[0]["status"] == "pending"

    fake2 = ReminderScheduler(_fake2_channel(store), store)
    _stub_conversations(fake2, "fake2")
    await fake2._send_reminder(user["user_id"], None, reminder["reminder_id"], "Test task")
    assert fake2.channel.sent[0]["chat_id"] == "ext-124"
    row = store.reminders[0]
    assert (row["status"], row["delivery_channel"], row["telegram_message_id"]) == (
        "sent", "fake2", None,
    )
    assert row["channel_message_ref"] == str(fake2.channel.sent[0]["message_id"])


async def test_reconciliation_schedules_on_the_primary_channel_only():
    store = FakeStore()
    user, reminder = await _second_app_primary(store)
    telegram = ReminderScheduler(FakeChannel(), store)
    fake2 = ReminderScheduler(_fake2_channel(store), store)
    await telegram.reconcile()
    await fake2.reconcile()

    def scheduled(scheduler):
        jobs = scheduler.scheduler.get_jobs()
        return any(job.id.endswith(reminder["reminder_id"]) for job in jobs)

    assert not scheduled(telegram)
    assert scheduled(fake2)


async def test_profile_without_telegram_is_scheduled_and_delivered_on_its_own_channel():
    """A participant whose only app is fake2 (no telegram_chat_id) still gets Reminders."""
    store = FakeStore()
    auth = "auth-no-telegram"
    store.activation_journeys.setdefault(auth, {"acknowledged_at": utc_now().isoformat()})
    await store.create_pairing_token("tok", auth, utc_now() + timedelta(minutes=10))
    assert await store.complete_channel_pairing("tok", "fake2", "ext-1") == {"status": "paired"}
    user = await store.get_user_by_channel_identity("fake2", "ext-1")
    assert user["telegram_chat_id"] is None
    task = await store.create_task(user["user_id"], "Test task")
    reminder = await store.create_reminder(
        task["task_id"], user["user_id"], (utc_now() + timedelta(minutes=5)).isoformat(),
    )

    fake2 = ReminderScheduler(_fake2_channel(store), store)
    _stub_conversations(fake2, "fake2")
    await fake2.reconcile()
    job = fake2.scheduler.get_job(f"{user['user_id']}:{reminder['reminder_id']}")
    assert job is not None and job.kwargs["chat_id"] is None

    await job.func(**job.kwargs)
    assert fake2.channel.sent[0]["chat_id"] == "ext-1"
    assert store.reminders[0]["status"] == "sent"
