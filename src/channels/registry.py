"""The messaging channels running in this process, and which one reaches a participant."""

from collections.abc import Iterable, Iterator

from src.channels.base import MessageChannel


class ChannelRegistry:
    """Every channel adapter this process runs, keyed by `channel_id` (ADR 0004).

    Proactive messages go only to the participant's primary channel. `for_user` returns that
    channel's adapter when it runs here, and None when it does not: then this process never sends.
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
        """The participant's primary channel's adapter, if it runs here and can deliver now.

        An adapter that is not ready (e.g. a gateway still connecting or down) is treated as not
        running: proactive messages wait pending instead of failing for good.
        """
        if not user:
            return None
        channel = self._channels.get(user.get("primary_channel", "telegram"))
        if channel is None or not getattr(channel, "ready", True):
            return None
        return channel

    def __iter__(self) -> Iterator[MessageChannel]:
        return iter(self._channels.values())

    def __len__(self) -> int:
        return len(self._channels)
