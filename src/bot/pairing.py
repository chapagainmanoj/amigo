"""Account pairing: link a messaging app to the verified dashboard account (ADR 0004)."""

import logging
import re

from src.channels.base import ConversationRef, MessageChannel, Recipient, endpoint_dict
from src.config import settings
from src.memory.pairing import PAIRING_TOKEN_HEX_LENGTH
from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# Telegram deep links arrive as "/start pair_<token>"; other apps type "/pair <token>".
_PAIRING_COMMAND = re.compile(r"^(?:/start pair_|/pair(?:\s+|$))(.*)$", re.DOTALL)
_INVALID_LINK = (
    "⚠️ The pairing link is invalid or has expired. "
    "Please request a new link from the dashboard."
)


def pairing_token(text: str) -> str | None:
    """The token of a pairing command, or None when the text is not one."""
    match = _PAIRING_COMMAND.match(text.strip())
    return match.group(1).strip() if match else None


async def handle_pairing(
    chat_id: Recipient, token: str, store: MemoryStore, channel: MessageChannel,
    *, conversation: ConversationRef | None = None,
) -> None:
    """Validate a pairing token and link this channel's address to its dashboard account."""
    app = channel.display_name
    if not re.fullmatch(rf"[0-9a-f]{{{PAIRING_TOKEN_HEX_LENGTH}}}", token):
        logger.warning("Pairing failed: malformed token channel=%s", channel.channel_id)
        await channel.send_message(chat_id=chat_id, conversation=conversation, text=_INVALID_LINK)
        return

    result = await store.complete_channel_pairing(token, channel.channel_id, str(chat_id))
    status = result["status"]

    if status == "invalid_token":
        logger.warning("Pairing failed: invalid token channel=%s", channel.channel_id)
        await channel.send_message(chat_id=chat_id, conversation=conversation, text=_INVALID_LINK)
        return

    if status == "conflict":
        logger.warning("Pairing conflict channel=%s", channel.channel_id)
        await channel.send_message(
            chat_id=chat_id,
            conversation=conversation,
            text=(
                f"⚠️ This dashboard account or {app} profile is already linked to another "
                "account. Return to the dashboard or contact support."
            ),
        )
        return

    if status in {"paired", "already_paired"}:
        user = await store.get_user_by_channel_identity(channel.channel_id, str(chat_id))
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
        logger.info("Pairing already complete channel=%s", channel.channel_id)
        await channel.send_message(
            chat_id=chat_id,
            conversation=conversation,
            text=f"{app} is already connected to this Amigo dashboard account.",
        )
        return

    logger.info("Pairing complete channel=%s", channel.channel_id)

    await channel.send_message(
        chat_id=chat_id,
        conversation=conversation,
        text=(
            f"🎉 Successfully paired! {app} is connected to your Amigo dashboard. "
            "No account identifiers are shown here. Return to the dashboard to finish your "
            f"profile and private test Reminder: {settings.dashboard_url}"
        ),
    )
