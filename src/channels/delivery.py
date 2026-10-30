"""Proactive delivery addressing: the single rule for where unprompted messages go (ADR 0004)."""

from src.channels.base import MessageChannel, Recipient


def reachable_here(channel: MessageChannel, user: dict | None) -> bool:
    """Proactive messages go only to the participant's primary channel.

    A process whose channel is not the primary never sends, even when the participant has an
    identity on it; the primary channel's own process delivers instead.
    """
    return bool(user) and user.get("primary_channel", "telegram") == channel.channel_id


async def proactive_recipient(channel: MessageChannel, user: dict | None) -> Recipient | None:
    """This channel's address for a proactive message to `user`, or None when it must not send."""
    if not reachable_here(channel, user):
        return None
    return await channel.recipient_for(user)
