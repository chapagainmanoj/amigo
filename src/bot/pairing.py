"""Account pairing and linking between Telegram and Supabase Auth."""

import logging
import re

from src.channels.base import ConversationRef, MessageChannel, endpoint_dict
from src.config import settings
from src.memory.pairing import PAIRING_TOKEN_HEX_LENGTH
from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)


async def handle_start_pairing(
    chat_id: int, token: str, store: MemoryStore, channel: MessageChannel,
    *, conversation: ConversationRef | None = None,
) -> None:
    """Validate a pairing token and link the Telegram user to the Supabase Auth ID."""
    if not re.fullmatch(rf"[0-9a-f]{{{PAIRING_TOKEN_HEX_LENGTH}}}", token):
        logger.warning(
            "Pairing failed: malformed token for chat_id %s",
            chat_id,
        )
        await channel.send_message(
            chat_id=chat_id,
            conversation=conversation,
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
            conversation=conversation,
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
            conversation=conversation,
            text=(
                "⚠️ This dashboard account or Telegram profile is already linked to another "
                "account. Return to the dashboard or contact support."
            ),
        )
        return

    if status in {"paired", "already_paired"}:
        user = await store.get_user_by_chat_id(chat_id)
        if user and channel.capabilities.threads:
            from src.conversations import ModeConversationService

            if conversation is not None:
                if not await channel.recipient_matches(conversation, chat_id):
                    raise ValueError("Pairing conversation does not match recipient")
                await store.save_mode_conversation(
                    user["user_id"], "daily", channel.channel_id, endpoint_dict(conversation)
                )
            conversation = await ModeConversationService(store, channel).ensure(
                user, chat_id=chat_id
            )

    if status == "already_paired":
        logger.info("Pairing already complete for chat_id %s", chat_id)
        await channel.send_message(
            chat_id=chat_id,
            conversation=conversation,
            text="Telegram is already connected to this Amigo dashboard account.",
        )
        return

    logger.info("Successfully paired Telegram chat_id %s", chat_id)

    await channel.send_message(
        chat_id=chat_id,
        conversation=conversation,
        text=(
            "🎉 Successfully paired! Telegram is connected to your Amigo dashboard. "
            "No account identifiers are shown here. Return to the dashboard to finish your "
            f"profile and private test Reminder: {settings.dashboard_url}"
        ),
    )
