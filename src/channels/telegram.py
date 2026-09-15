"""Telegram implementation of MessageChannel."""

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from src.config import settings

logger = logging.getLogger(__name__)


class TelegramChannel:
    """Telegram Bot API implementation of MessageChannel protocol."""

    def __init__(self):
        self._bot: Bot | None = None

    @property
    def bot(self) -> Bot:
        """Build the Bot on first use rather than at construction.

        python-telegram-bot rejects an empty token outright, so building it in __init__ meant
        importing src.main required a real token — including during test collection, which never
        dials Telegram.

        Production is unaffected, but not because the timing is unchanged: validate_runtime_
        configuration already rejects a malformed TELEGRAM_BOT_TOKEN at import, before anything
        here is reached. What does change is development, where that check does not run — the
        app used to refuse to import with a bad token and now starts, logs the failed webhook
        setup as a warning, and 500s on webhook delivery instead.

        getattr, not self._bot, so an instance built with __new__ (as tests/test_channels.py
        does) reads as unset rather than raising AttributeError.
        """
        if getattr(self, "_bot", None) is None:
            self._bot = Bot(token=settings.telegram_bot_token)
        return self._bot

    @bot.setter
    def bot(self, value: Bot) -> None:
        """Tests substitute a double here; keep assignment working."""
        self._bot = value

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> int | None:
        """Send message via Telegram. Returns message_id for later editing.

        Uses plain text by default — safer for dynamic LLM/task content.
        """
        reply_markup = None
        if buttons:
            keyboard = [
                [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])
                 for btn in row]
                for row in buttons
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        msg = await self.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        return msg.message_id

    async def edit_message_buttons(
        self,
        chat_id: str | int,
        message_id: int,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> None:
        """Edit inline keyboard on existing message. None removes buttons."""
        reply_markup = None
        if buttons:
            keyboard = [
                [InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])
                 for btn in row]
                for row in buttons
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        await self.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
        )
