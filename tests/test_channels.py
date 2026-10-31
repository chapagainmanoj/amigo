"""Message channel adapter tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram import InlineKeyboardMarkup

from src.channels.cli import CLIChannel
from src.channels.telegram import TelegramChannel


async def test_cli_channel_tracks_resolves_and_clears_buttons(capsys):
    channel = CLIChannel()
    buttons = [
        [
            {"text": "Done", "callback_data": "done:1"},
            {"text": "Later", "callback_data": "later:1"},
        ]
    ]

    message_id = await channel.send_message(123, "Reminder", buttons=buttons)

    assert channel.pending_buttons == buttons[0]
    assert channel.resolve_button("2") == "later:1"
    assert channel.pending_buttons == []

    await channel.send_message(123, "Plain message")

    assert channel.pending_buttons == []
    assert message_id is not None
    assert "Reminder" in capsys.readouterr().out


async def test_cli_channel_rejects_invalid_button_choices():
    channel = CLIChannel()
    await channel.send_message(
        123,
        "Reminder",
        buttons=[[{"text": "Done", "callback_data": "done:1"}]],
    )

    assert channel.resolve_button("not-a-number") is None
    assert channel.resolve_button("9") is None
    assert channel.resolve_button("1") == "done:1"


async def test_cli_channel_edit_buttons_clears_matching_pending_message():
    channel = CLIChannel()
    message_id = await channel.send_message(
        123,
        "Reminder",
        buttons=[[{"text": "Done", "callback_data": "done:1"}]],
    )

    await channel.edit_message_buttons(123, message_id, buttons=None)

    assert channel.pending_buttons == []


async def test_telegram_channel_converts_buttons_to_inline_keyboard_markup():
    channel = TelegramChannel.__new__(TelegramChannel)
    channel.bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=42))
    )
    buttons = [[{"text": "Done", "callback_data": "done:1"}]]

    message_id = await channel.send_message(123, "Reminder", buttons=buttons)

    assert message_id == 42
    channel.bot.send_message.assert_awaited_once()
    kwargs = channel.bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 123
    assert kwargs["text"] == "Reminder"
    assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == "Done"
    assert button.callback_data == "done:1"


async def test_telegram_channel_edit_buttons_removes_markup():
    channel = TelegramChannel.__new__(TelegramChannel)
    channel.bot = SimpleNamespace(edit_message_reply_markup=AsyncMock())

    await channel.edit_message_buttons(123, 42, buttons=None)

    channel.bot.edit_message_reply_markup.assert_awaited_once_with(
        chat_id=123,
        message_id=42,
        reply_markup=None,
    )


async def test_telegram_channel_edit_buttons_converts_markup():
    channel = TelegramChannel.__new__(TelegramChannel)
    channel.bot = SimpleNamespace(edit_message_reply_markup=AsyncMock())

    await channel.edit_message_buttons(
        123,
        42,
        buttons=[[{"text": "Skip", "callback_data": "skip:1"}]],
    )

    kwargs = channel.bot.edit_message_reply_markup.await_args.kwargs
    assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == "Skip"
    assert button.callback_data == "skip:1"


async def test_cli_recipient_comes_from_its_own_channel_identity():
    from src.memory.memory_store import InMemoryStore

    store = InMemoryStore()
    user = await store.create_user(12345)
    store._identity_state.link(user["user_id"], "cli", "dev-1")
    assert await CLIChannel(store).recipient_for(user) == "dev-1"
    assert await CLIChannel().recipient_for(user) == "cli"


def test_every_adapter_declares_the_channel_lifecycle():
    """ADR 0005: ready, connect_link, start and close are part of MessageChannel."""
    import inspect

    from scripts.smoke_check import SmokeChannel
    from src.channels.discord import DiscordChannel
    from src.channels.telegram import TelegramChannel
    from tests.fakes import FakeChannel, FakeStore

    adapters = [
        TelegramChannel(token="unused"), CLIChannel(),
        DiscordChannel(FakeStore(), token="unused"), FakeChannel(), SmokeChannel(),
    ]
    for adapter in adapters:
        assert isinstance(adapter.ready, bool), adapter
        assert adapter.connect_link is None or isinstance(adapter.connect_link, str)
        assert inspect.iscoroutinefunction(adapter.start), adapter
        assert inspect.iscoroutinefunction(adapter.close), adapter
    assert [adapter.ready for adapter in adapters] == [True, True, False, True, True]


async def test_telegram_start_initializes_the_bot(monkeypatch):
    """ADR 0005: Telegram's start() is its initialize()."""
    from unittest.mock import AsyncMock

    from src.channels.telegram import TelegramChannel

    channel = TelegramChannel(token="unused")
    channel.initialize = AsyncMock(return_value="amigo_bot")
    monkeypatch.setattr("src.config.settings.app_env", "production")
    await channel.start()
    channel.initialize.assert_awaited_once_with(production=True)
