"""Two channels in one process: proactive sends follow the primary channel (ADR 0004)."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.channels.delivery import proactive_recipient
from src.channels.registry import ChannelRegistry
from src.handoffs import HandoffController
from src.scheduler.reminders import ReminderScheduler
from src.utils import utc_now
from tests.fakes import FakeChannel, FakeStore


def _fake2():
    return FakeChannel(channel_id="fake2")


def test_registry_rejects_duplicates_and_empty_and_wraps_one_channel():
    telegram = FakeChannel()
    with pytest.raises(ValueError):
        ChannelRegistry([telegram, FakeChannel()])
    with pytest.raises(ValueError):
        ChannelRegistry([])
    registry = ChannelRegistry.of(telegram)
    assert ChannelRegistry.of(registry) is registry
    assert registry.default is telegram and len(registry) == 1


def test_for_user_is_the_primary_channel_only_when_it_runs_here():
    telegram, fake2 = FakeChannel(), _fake2()
    registry = ChannelRegistry([telegram, fake2])
    assert registry.for_user({"primary_channel": "fake2"}) is fake2
    assert registry.for_user({"primary_channel": "telegram"}) is telegram
    assert registry.for_user({"user_id": "u"}) is telegram  # legacy rows default to Telegram
    assert registry.for_user({"primary_channel": "elsewhere"}) is None
    assert registry.for_user(None) is None


async def test_proactive_recipient_uses_the_primary_adapter_address():
    store = FakeStore()
    user = await store.create_user(51001)
    store._identity_state.link(user["user_id"], "fake2", "ext-51001")
    fake2 = _fake2()

    async def recipient_for(user):
        return (await store.list_channel_identities(user["user_id"])).get("fake2")

    fake2.recipient_for = recipient_for
    registry = ChannelRegistry([FakeChannel(), fake2])
    await store.set_primary_channel(user["user_id"], "fake2")
    channel, recipient = await proactive_recipient(
        registry, await store.get_user_by_id(user["user_id"])
    )
    assert (channel, recipient) == (fake2, "ext-51001")


async def test_one_scheduler_delivers_on_whichever_primary_channel_the_participant_chose():
    store = FakeStore()
    user = await store.create_user(51002)
    store._identity_state.link(user["user_id"], "fake2", "ext-51002")
    telegram, fake2 = FakeChannel(), _fake2()

    async def recipient_for(user):
        return (await store.list_channel_identities(user["user_id"])).get("fake2")

    fake2.recipient_for = recipient_for
    scheduler = ReminderScheduler(ChannelRegistry([telegram, fake2]), store)
    task = await store.create_task(user["user_id"], "Stretch")

    async def deliver():
        reminder = await store.create_reminder(
            task["task_id"], user["user_id"], (utc_now() + timedelta(minutes=5)).isoformat(),
        )
        await scheduler._send_reminder(user["user_id"], None, reminder["reminder_id"], "Stretch")
        return next(r for r in store.reminders if r["reminder_id"] == reminder["reminder_id"])

    first = await deliver()
    assert (len(telegram.sent), len(fake2.sent)) == (1, 0)
    assert first["delivery_channel"] == "telegram" and first["telegram_message_id"] is not None

    await store.set_primary_channel(user["user_id"], "fake2")
    second = await deliver()
    assert (len(telegram.sent), len(fake2.sent)) == (1, 1)
    assert fake2.sent[0]["chat_id"] == "ext-51002"
    assert (second["delivery_channel"], second["telegram_message_id"]) == ("fake2", None)
    assert second["channel_message_ref"] == str(fake2.sent[0]["message_id"])


async def test_handoff_recovery_runs_only_on_the_primary_channels_controller():
    store = FakeStore()
    user = await store.create_user(51003)
    store._identity_state.link(user["user_id"], "fake2", "ext-51003")
    await store.set_primary_channel(user["user_id"], "fake2")
    telegram, fake2 = FakeChannel(), _fake2()
    registry = ChannelRegistry([telegram, fake2])
    controllers = {
        channel.channel_id: HandoffController(
            store, channel, SimpleNamespace(), SimpleNamespace(), SimpleNamespace(),
            channels=registry,
        )
        for channel in registry
    }
    pending = {"user_id": user["user_id"], "handoff_id": "h-1"}
    for controller in controllers.values():
        controller.retire_unavailable = AsyncMock()
        controller.execute = AsyncMock()
        controller._activated = AsyncMock(return_value=True)
        await controller._recover_execution(None, pending)

    controllers["telegram"].execute.assert_not_awaited()
    controllers["fake2"].execute.assert_awaited_once()


async def test_handoff_recovery_waits_when_the_primary_channel_runs_elsewhere():
    store = FakeStore()
    user = await store.create_user(51004)
    store._identity_state.link(user["user_id"], "fake2", "ext-51004")
    await store.set_primary_channel(user["user_id"], "fake2")
    telegram = FakeChannel()
    controller = HandoffController(
        store, telegram, SimpleNamespace(), SimpleNamespace(), SimpleNamespace(),
        channels=ChannelRegistry([telegram]),
    )
    controller.retire_unavailable = AsyncMock()
    controller.execute = AsyncMock()
    await controller._recover_execution(None, {"user_id": user["user_id"], "handoff_id": "h-2"})
    # Neither sent on Telegram nor retired: the process running fake2 recovers it.
    controller.execute.assert_not_awaited()
    controller.retire_unavailable.assert_not_awaited()


async def test_dashboard_mode_switch_opens_on_the_primary_channel(monkeypatch):
    from src import main

    store = FakeStore()
    user = await store.create_user(51005)
    store._identity_state.link(user["user_id"], "fake2", "ext-51005")
    await store.set_primary_channel(user["user_id"], "fake2")
    user = await store.get_user_by_id(user["user_id"])
    telegram, fake2 = FakeChannel(), _fake2()
    fake2.recipient_for = AsyncMock(return_value="ext-51005")
    opened = {
        channel_id: SimpleNamespace(turn_processor=SimpleNamespace(
            open_mode=AsyncMock(return_value=(True, f"opened on {channel_id}"))
        ))
        for channel_id in ("telegram", "fake2")
    }
    monkeypatch.setattr(main, "channels", ChannelRegistry([telegram, fake2]))
    monkeypatch.setattr(main, "handlers_by_channel", opened)
    assert await main._open_mode(user, "coach") == (True, "opened on fake2")
    opened["fake2"].turn_processor.open_mode.assert_awaited_once_with(
        "ext-51005", user, "coach", note=None
    )
    opened["telegram"].turn_processor.open_mode.assert_not_awaited()

    monkeypatch.setattr(main, "channels", ChannelRegistry([telegram]))
    assert await main._open_mode(user, "coach") is None
