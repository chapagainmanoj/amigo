"""Account pairing and linking between Telegram and Supabase Auth."""

import logging
import re

from src.channels.base import MessageChannel
from src.memory.pairing import PAIRING_TOKEN_HEX_LENGTH
from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)


async def handle_start_pairing(
    chat_id: int, token: str, store: MemoryStore, channel: MessageChannel
) -> None:
    """Validate a pairing token and link the Telegram user to the Supabase Auth ID."""
    if not re.fullmatch(rf"[0-9a-f]{{{PAIRING_TOKEN_HEX_LENGTH}}}", token):
        logger.warning(
            "Pairing failed: malformed token for chat_id %s",
            chat_id,
        )
        await channel.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ The pairing link is invalid or has expired. "
                "Please request a new link from the dashboard."
            ),
        )
        return

    result = await store.complete_pairing(token, chat_id)
    status = result["status"]

    if status == "invalid_token":
        logger.warning("Pairing failed: invalid token for chat_id %s", chat_id)
        await channel.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ The pairing link is invalid or has expired. "
                "Please request a new link from the dashboard."
            ),
        )
        return

    if status == "conflict":
        logger.warning("Pairing conflict for chat_id %s", chat_id)
        await channel.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ This dashboard account or Telegram profile is already linked to another "
                "account. Return to the dashboard or contact support."
            ),
        )
        return

    if status == "already_paired":
        logger.info("Pairing already complete for chat_id %s", chat_id)
        await channel.send_message(
            chat_id=chat_id,
            text="Telegram is already connected to this Amigo dashboard account.",
        )
        return

    logger.info("Successfully paired Telegram chat_id %s", chat_id)

    await channel.send_message(
        chat_id=chat_id,
        text=(
            "🎉 Successfully paired! Telegram is connected to your Amigo dashboard. "
            "Send another message to finish setup and create your first task."
        ),
    )
