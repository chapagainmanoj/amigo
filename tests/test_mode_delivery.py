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


@pytest.mark.parametrize("recovery", [False, True])
async def test_delivery_resolves_daily_conversation_after_scheduling(recovery):
    store, channel = FakeStore(), FakeChannel(threads=True)
    user, reminder = await _reminder(store)
    scheduler = ReminderScheduler(channel, store)
    original = ConversationRef(channel.channel_id, {"chat_id": 123, "opaque": "old"})
    current = ConversationRef(channel.channel_id, {"chat_id": 123, "opaque": "current"})
    service = type("ConversationService", (), {})()
    service.ensure = AsyncMock(return_value=original)
    scheduler._mode_conversations = service
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
    scheduler._mode_conversations = type("ConversationService", (), {})()
    scheduler._mode_conversations.ensure = AsyncMock(return_value=None)
    await scheduler._send_reminder(user["user_id"], 123, reminder["reminder_id"], "Test task")
    assert channel.sent[0]["chat_id"] == 456
    assert scheduler._mode_conversations.ensure.call_args.kwargs == {"chat_id": 456}


async def test_different_primary_channel_is_not_sent_through_old_channel(monkeypatch):
    store, channel = FakeStore(), FakeChannel()
    user, reminder = await _reminder(store)
    monkeypatch.setattr(store, "get_user_by_id", AsyncMock(return_value={
        **user, "primary_channel": "unavailable-channel",
    }))
    scheduler = ReminderScheduler(channel, store)
    await scheduler._send_reminder(user["user_id"], 123, reminder["reminder_id"], "Test task")
    assert not channel.sent
    attempt = next(iter(store.reminder_delivery_attempts.values()))
    assert attempt["result"] == "error"


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
