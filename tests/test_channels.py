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
