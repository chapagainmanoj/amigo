"""Proactive delivery addressing: the single rule for where unprompted messages go (ADR 0004)."""

from src.channels.base import MessageChannel, Recipient
from src.channels.registry import ChannelRegistry


def reachable_here(channels: ChannelRegistry, user: dict | None) -> bool:
    """Proactive messages go only to the participant's primary channel.

    A process that does not run the primary channel never sends, even when the participant has
    an identity on one of its channels; the process running the primary channel delivers instead.
    """
    return channels.for_user(user) is not None


async def proactive_recipient(
    channels: ChannelRegistry, user: dict | None
) -> tuple[MessageChannel, Recipient] | None:
    """The primary adapter and its address for `user`; None when this process must not send."""
    channel = channels.for_user(user)
    if channel is None:
        return None
    recipient = await channel.recipient_for(user)
    return None if recipient is None else (channel, recipient)
