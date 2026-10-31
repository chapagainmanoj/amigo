"""The messaging channels running in this process, and where unprompted messages go (ADR 0004)."""

from collections.abc import Iterable, Iterator

from src.access import may_use_channel
from src.channels.base import MessageChannel, Recipient


class ChannelRegistry:
    """Every channel adapter this process runs, keyed by `channel_id` (ADR 0004).

    The one rule for proactive messages (Reminders, recovery summaries, Coach nudges, handoff
    recovery): they go only to the participant's primary channel, and only when its adapter runs
    here, is ready, and the participant may use it. Otherwise this process never sends and the
    message waits pending; it never falls back to another app.
    """

    def __init__(self, channels: Iterable[MessageChannel]):
        self._channels: dict[str, MessageChannel] = {}
        for channel in channels:
            if channel.channel_id in self._channels:
                raise ValueError(f"Duplicate channel {channel.channel_id!r}")
            self._channels[channel.channel_id] = channel
        if not self._channels:
            raise ValueError("A process runs at least one channel")

    @classmethod
    def of(cls, channels: "MessageChannel | ChannelRegistry") -> "ChannelRegistry":
        """Accept one adapter where a registry is expected (single-channel processes, tests)."""
        return channels if isinstance(channels, ChannelRegistry) else cls([channels])

    @property
    def default(self) -> MessageChannel:
        """The first registered channel; the process's main ingress."""
        return next(iter(self._channels.values()))

    def get(self, channel_id: str) -> MessageChannel | None:
        return self._channels.get(channel_id)

    def for_user(self, user: dict | None) -> MessageChannel | None:
        """The adapter that may deliver to this participant now, or None."""
        if not user:
            return None
        channel = self._channels.get(user.get("primary_channel", "telegram"))
        if channel is None or not channel.ready:
            return None
        return channel if may_use_channel(user, channel.channel_id) else None

    async def address(self, user: dict | None) -> tuple[MessageChannel, Recipient] | None:
        """The adapter and its address for a proactive message, or None when none may be sent."""
        channel = self.for_user(user)
        if channel is None:
            return None
        recipient = await channel.recipient_for(user)
        return None if recipient is None else (channel, recipient)

    def __iter__(self) -> Iterator[MessageChannel]:
        return iter(self._channels.values())

    def __len__(self) -> int:
        return len(self._channels)
