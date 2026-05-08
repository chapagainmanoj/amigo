"""Telegram implementation of MessageChannel."""

import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from src.config import settings

logger = logging.getLogger(__name__)


class TelegramChannel:
    """Telegram Bot API implementation of MessageChannel protocol."""

    def __init__(self):
        self.bot = Bot(token=settings.telegram_bot_token)

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
