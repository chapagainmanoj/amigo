"""Discord adapter: decoding, DM sending, buttons and the two-app proof, all offline (ADR 0004)."""

import itertools
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from src.activation import ACTIVATION_POLICY_VERSION
from src.bot.handlers import BotHandlers
from src.bot.update_claims import ChannelUpdateCoordinator
from src.channels.discord import (
    MESSAGE_LIMIT,
    DiscordChannel,
    button_rows,
    decode_interaction,
    decode_message,
    split_text,
)
from src.channels.registry import ChannelRegistry
from src.memory.sessions import SessionManager
from src.scheduler.reminders import ReminderScheduler
from src.utils import utc_now
from tests.fakes import FakeChannel, FakeStore

_ids = itertools.count(9_000_000_000_000_000)


class FakeDM:
    def __init__(self):
        self.sent: list[dict] = []
        self.edited: list[dict] = []

    async def send(self, content, **kwargs):
        message = SimpleNamespace(id=next(_ids))
        self.sent.append({"content": content, "id": message.id, **kwargs})
        return message

    def get_partial_message(self, message_id):
        async def edit(**kwargs):
            self.edited.append({"message_id": message_id, **kwargs})

        return SimpleNamespace(edit=edit)


class FakeClient:
    def __init__(self):
        self.dms: dict[int, FakeDM] = {}
        self.fetches = 0

    def get_user(self, user_id):
        return None

    async def fetch_user(self, user_id):
        self.fetches += 1
        dm = self.dms.setdefault(user_id, FakeDM())

        async def create_dm():
            return dm

        return SimpleNamespace(dm_channel=None, create_dm=create_dm)


def _discord(store=None):
    return DiscordChannel(store or FakeStore(), token="unused", client=FakeClient())


def _message(content="hi", *, author_id=555, bot=False, guild=None, message_id=1001):
    return SimpleNamespace(
        id=message_id, content=content, guild=guild,
        author=SimpleNamespace(id=author_id, bot=bot),
    )


def _interaction(custom_id="done:r1", *, kind=discord.InteractionType.component, guild_id=None):
    response = SimpleNamespace(is_done=lambda: False, defer=AsyncMock())
    return SimpleNamespace(
        id=2002, type=kind, guild_id=guild_id, data={"custom_id": custom_id},
        message=SimpleNamespace(id=3003), user=SimpleNamespace(id=555), response=response,
    )


# ── Decoding ──

def test_dm_text_decodes_and_everything_else_is_ignored():
    update = decode_message(_message("hello"))
    assert (update.kind, update.chat_id, update.text, update.update_id) == (
        "message", "555", "hello", 1001,
    )
    assert decode_message(_message(guild=SimpleNamespace(id=1))) is None
    assert decode_message(_message(bot=True)) is None  # includes Amigo's own messages
    assert decode_message(_message("")) is None


def test_dm_button_press_decodes_as_callback():
    update = decode_interaction(_interaction("snooze:r9"))
    assert (update.kind, update.chat_id, update.data, update.message_id) == (
        "callback_query", "555", "snooze:r9", 3003,
    )
    assert decode_interaction(_interaction(guild_id=1)) is None
    command = discord.InteractionType.application_command
    assert decode_interaction(_interaction(kind=command)) is None
    assert decode_interaction(_interaction("")) is None


# ── Text and buttons ──

def test_long_text_splits_under_the_limit_at_line_boundaries():
    text = "\n".join(f"line {i} " + "x" * 90 for i in range(60))
    parts = split_text(text)
    assert len(parts) > 1 and all(len(part) <= MESSAGE_LIMIT for part in parts)
    assert all(part.startswith("line ") for part in parts)
    assert "".join(parts).replace("\n", "") == text.replace("\n", "")
    assert sum(len(part) for part in split_text("y" * 4100)) == 4100
    assert split_text("short") == ["short"]
    assert split_text("  \n ") == []


def test_split_keeps_code_blocks_closed_and_indentation():
    code = "\n".join(f"    line {i}" for i in range(300))
    parts = split_text(f"Here:\n```\n{code}\n```\nDone")
    assert len(parts) > 1 and all(len(part) <= MESSAGE_LIMIT for part in parts)
    assert all(part.count("```") % 2 == 0 for part in parts)
    assert parts[1].startswith("```\n    line")


def test_buttons_rechunk_to_discord_rows_and_reject_what_cannot_fit():
    row = [{"text": f"M{i}", "callback_data": f"mode:m{i}"} for i in range(7)]
    assert [len(r) for r in button_rows([row])] == [5, 2]
    with pytest.raises(ValueError):
        button_rows([row] * 4)  # 28 buttons
    with pytest.raises(ValueError):
        button_rows([[{"text": "x", "callback_data": "c" * 101}]])


# ── Sending ──

async def test_send_splits_puts_buttons_on_last_part_and_disables_mentions():
    channel = _discord()
    buttons = [[{"text": "Done", "callback_data": "done:r1"}]]
    message_id = await channel.send_message("555", "z" * 2500, buttons=buttons)
    dm = channel.client.dms[555]
    assert [len(item["content"]) for item in dm.sent] == [1996, 504]
    assert "view" not in dm.sent[0] and dm.sent[1]["view"].children[0].custom_id == "done:r1"
    assert all(
        item["allowed_mentions"].to_dict() == discord.AllowedMentions.none().to_dict()
        for item in dm.sent
    )
    assert message_id == dm.sent[-1]["id"]
    await channel.send_message("555", "again")
    assert channel.client.fetches == 1  # DM channel cached


async def test_edit_buttons_clears_the_view():
    channel = _discord()
    await channel.edit_message_buttons("555", 3003, buttons=None)
    assert channel.client.dms[555].edited == [{"message_id": 3003, "view": None}]


async def test_recipient_is_the_linked_discord_identity():
    store = FakeStore()
    user = await store.create_user(61001)
    channel = _discord(store)
    assert await channel.recipient_for(user) is None
    store._identity_state.link(user["user_id"], "discord", "555")
    assert await channel.recipient_for(user) == "555"


async def test_one_failing_event_never_reaches_the_gateway_loop():
    channel = _discord()
    channel.on_update = AsyncMock(side_effect=RuntimeError("boom"))
    await channel._dispatch(decode_message(_message()), None)  # logged, not raised


# ── Two apps in one process: the proof ──

async def _two_app_process(monkeypatch):
    monkeypatch.setattr(DiscordChannel, "ready", property(lambda self: True))
    monkeypatch.setattr("src.config.settings.access_mode", "registered")
    monkeypatch.setattr("src.config.settings.allowed_telegram_chat_ids", "61002")
    store = FakeStore()
    await store.acknowledge_activation_terms("auth-61002", ACTIVATION_POLICY_VERSION)
    user = await store.create_user(61002)
    await store.update_user(user["user_id"], {"supabase_auth_id": "auth-61002"})
    store.get_activation_state = AsyncMock(return_value={"completed": True})
    telegram, discord_channel = FakeChannel(), _discord(store)
    registry = ChannelRegistry([telegram, discord_channel])
    scheduler = ReminderScheduler(registry, store)
    sessions = SessionManager(store)
    handlers = BotHandlers(discord_channel, store, sessions, scheduler, channels=registry)
    telegram_coordinator = ChannelUpdateCoordinator(store)
    coordinator = ChannelUpdateCoordinator(
        store, telegram_coordinator.serializer, channel_id="discord"
    )

    async def deliver(event):
        update = decode_message(event)
        return await coordinator.run(
            update_id=update.update_id, chat_id=update.chat_id, update_kind=update.kind,
            process=lambda: handlers.handle_message(
                update.chat_id, update.text, update_id=update.update_id
            ),
        )

    return SimpleNamespace(
        store=store, user=user, telegram=telegram, discord=discord_channel,
        scheduler=scheduler, handlers=handlers, coordinator=coordinator, deliver=deliver,
    )


async def test_full_access_participant_pairs_discord_chats_there_and_gets_reminders_there(
    monkeypatch,
):
    env = await _two_app_process(monkeypatch)
    token = f"{61:032x}"
    await env.store.create_pairing_token(token, "auth-61002", utc_now() + timedelta(minutes=10))

    assert (await env.deliver(_message(f"/pair {token}", message_id=1))).outcome == "completed"
    dm = env.discord.client.dms[555]
    assert "Discord is connected" in dm.sent[-1]["content"]
    assert await env.store.list_channel_identities(env.user["user_id"]) == {
        "discord": "555", "telegram": "61002",
    }

    await env.deliver(_message("/help", message_id=2))
    assert "/mode" in dm.sent[-1]["content"]
    # A gateway resume that redelivers the same message is claimed once.
    assert (await env.deliver(_message("/help", message_id=2))).outcome == "duplicate"

    await env.store.set_primary_channel(env.user["user_id"], "discord")
    task = await env.store.create_task(env.user["user_id"], "Stretch")
    reminder = await env.store.create_reminder(
        task["task_id"], env.user["user_id"], (utc_now() + timedelta(minutes=5)).isoformat(),
    )
    env.scheduler._mode_conversations["discord"] = SimpleNamespace(
        ensure=AsyncMock(return_value=None)
    )
    await env.scheduler._send_reminder(
        env.user["user_id"], None, reminder["reminder_id"], "Stretch"
    )
    assert not env.telegram.sent
    view = dm.sent[-1]["view"]
    assert any(item.custom_id.endswith(reminder["reminder_id"]) for item in view.children)
    row = next(r for r in env.store.reminders if r["reminder_id"] == reminder["reminder_id"])
    assert (row["status"], row["delivery_channel"]) == ("sent", "discord")
    assert row["channel_message_ref"] == str(dm.sent[-1]["id"])


async def test_unlinked_or_non_full_access_discord_users_get_nothing_but_a_refusal(monkeypatch):
    env = await _two_app_process(monkeypatch)
    await env.deliver(_message("hello", author_id=777, message_id=5))
    dm = env.discord.client.dms[777]
    assert "isn't open" in dm.sent[-1]["content"]

    monkeypatch.setattr("src.config.settings.allowed_telegram_chat_ids", "1")
    token = f"{62:032x}"
    await env.store.create_pairing_token(token, "auth-61002", utc_now() + timedelta(minutes=10))
    await env.deliver(_message(f"/pair {token}", message_id=6))
    assert "full access" in env.discord.client.dms[555].sent[-1]["content"]
    assert "discord" not in await env.store.list_channel_identities(env.user["user_id"])


async def test_button_presses_are_acknowledged_before_the_claim(monkeypatch):
    from src import main

    order = []
    store = FakeStore()
    original = store.claim_channel_update

    async def claim(*args, **kwargs):
        order.append("claim")
        return await original(*args, **kwargs)

    store.claim_channel_update = claim
    coordinator = ChannelUpdateCoordinator(store, channel_id="discord")
    handlers = SimpleNamespace(handle_callback=AsyncMock(), handle_message=AsyncMock())
    monkeypatch.setattr(main, "discord_channel", SimpleNamespace(channel_id="discord"))
    monkeypatch.setattr(main, "handlers_by_channel", {"discord": handlers})
    monkeypatch.setattr(main, "coordinators", {"discord": coordinator})

    async def acknowledge():
        order.append("ack")

    await main._discord_update(decode_interaction(_interaction("done:r1")), acknowledge)
    assert order == ["ack", "claim"]
    handlers.handle_callback.assert_awaited_once()
    assert handlers.handle_callback.call_args.kwargs["data"] == "done:r1"


async def test_turns_from_telegram_and_discord_for_one_participant_never_overlap():
    import asyncio

    store = FakeStore()
    user = await store.create_user(61003)
    store._identity_state.link(user["user_id"], "discord", "555")
    telegram = ChannelUpdateCoordinator(store)
    discord_coordinator = ChannelUpdateCoordinator(
        store, telegram.serializer, channel_id="discord"
    )
    active, overlaps, entered = [], [], asyncio.Event()

    async def turn(name):
        if active:
            overlaps.append(name)
        active.append(name)
        entered.set()
        await asyncio.sleep(0.01)
        active.remove(name)

    first = asyncio.create_task(telegram.run(
        update_id=1, chat_id=61003, update_kind="message", process=lambda: turn("telegram"),
    ))
    await entered.wait()
    second = asyncio.create_task(discord_coordinator.run(
        update_id=2, chat_id="555", update_kind="message", process=lambda: turn("discord"),
    ))
    results = await asyncio.gather(first, second)
    assert [result.outcome for result in results] == ["completed", "completed"]
    assert overlaps == []



async def test_empty_text_is_never_sent():
    channel = _discord()
    assert await channel.send_message("555", "   ") is None
    assert channel.client.fetches == 0


async def test_a_failed_acknowledgement_still_processes_the_press(monkeypatch):
    channel = DiscordChannel(FakeStore(), token="unused")  # real discord.py client, no network
    seen = []

    async def on_update(update, acknowledge):
        await acknowledge()
        seen.append(update.data)

    channel.on_update = on_update
    interaction = _interaction("done:r1")
    response = SimpleNamespace(status=404, reason="Not Found")
    interaction.response.defer = AsyncMock(
        side_effect=discord.NotFound(response, {"code": 10062, "message": "Unknown interaction"})
    )
    handler = channel.client.on_interaction
    await handler(interaction)
    assert seen == ["done:r1"]


def test_real_client_listens_to_direct_messages_only():
    channel = DiscordChannel(FakeStore(), token="unused")
    intents = channel.client.intents
    assert intents.dm_messages and not intents.guild_messages and not intents.message_content
    assert channel.ready is False  # not connected: Discord-primary messages wait pending


async def test_not_ready_primary_adapter_leaves_reminders_pending():
    store = FakeStore()
    user = await store.create_user(61004)
    store._identity_state.link(user["user_id"], "discord", "555")
    await store.set_primary_channel(user["user_id"], "discord")
    discord_channel = _discord(store)  # never started, so not ready
    scheduler = ReminderScheduler(ChannelRegistry([FakeChannel(), discord_channel]), store)
    task = await store.create_task(user["user_id"], "Stretch")
    reminder = await store.create_reminder(
        task["task_id"], user["user_id"], (utc_now() + timedelta(minutes=5)).isoformat(),
    )
    await scheduler._send_reminder(user["user_id"], None, reminder["reminder_id"], "Stretch")
    assert store.reminders[0]["status"] == "pending"
    assert channel_sent(discord_channel) == 0


def channel_sent(channel):
    return sum(len(dm.sent) for dm in channel.client.dms.values())


async def test_gateway_exit_is_logged_and_shutdown_drains_inflight_turns(caplog):
    import asyncio

    channel = _discord()
    release, finished = asyncio.Event(), []

    async def on_update(update, acknowledge):
        await release.wait()
        finished.append(update.text)

    channel.on_update = on_update
    channel.client.close = AsyncMock()
    turn = asyncio.create_task(channel._dispatch(decode_message(_message("hi")), None))
    await asyncio.sleep(0)
    closing = asyncio.create_task(channel.close(drain_timeout=2))
    await asyncio.sleep(0)
    await channel._dispatch(decode_message(_message("late", message_id=7)), None)
    release.set()
    await asyncio.gather(turn, closing)
    assert finished == ["hi"]  # in-flight Turn finished; the late event was not taken
    channel.client.close.assert_awaited_once()

    from src.channels.discord import _log_gateway_exit

    async def boom():
        raise RuntimeError("gateway")

    failed = asyncio.create_task(boom())
    await asyncio.sleep(0)
    _log_gateway_exit(failed)
    assert "Discord gateway stopped: RuntimeError" in caplog.text
