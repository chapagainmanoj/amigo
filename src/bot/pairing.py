"""Account pairing and linking between Telegram and Supabase Auth."""

import logging

from src.channels.base import MessageChannel
from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)


async def handle_start_pairing(
    chat_id: int, token: str, store: MemoryStore, channel: MessageChannel
) -> None:
    """Validate a pairing token and link the Telegram user to the Supabase Auth ID."""
    token_row = await store.consume_pairing_token(token)
    if not token_row:
        logger.warning(
            "Pairing failed: Invalid, expired, or consumed token %s for chat_id %s",
            token,
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

    auth_id = token_row["supabase_auth_id"]

    # Get or create the user profile for this Telegram chat ID.
    user = await store.get_user_by_chat_id(chat_id)
    if not user:
        # Create user during pairing
        user = await store.create_user(chat_id)

    # Update the user profile with the supabase auth ID.
    await store.update_user(user["user_id"], {"supabase_auth_id": auth_id})
    logger.info(
        "Successfully paired Telegram chat_id %s to Supabase Auth ID %s", chat_id, auth_id
    )

    await channel.send_message(
        chat_id=chat_id,
        text="🎉 Successfully paired! You can now access your Amigo Web Dashboard.",
    )
