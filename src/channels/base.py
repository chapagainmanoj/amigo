"""Channel-neutral conversation addresses, capability declarations and delivery protocol."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Protocol

# A channel's own address for one participant: Telegram uses integer chat ids, other channels
# opaque strings. Values are only ever compared within the channel that produced them.
type Recipient = str | int


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ConversationRef:
    """An immutable channel endpoint; provider identifiers never become participant identity."""

    channel: str
    endpoint: Mapping[str, Any]

    def __post_init__(self):
        if (
            not isinstance(self.channel, str)
            or not self.channel
            or self.channel != self.channel.strip()
        ):
            raise ValueError("Conversation requires a channel")
        if not isinstance(self.endpoint, Mapping) or not all(
            isinstance(key, str) for key in self.endpoint
        ):
            raise ValueError("Conversation endpoint requires a JSON object")
        try:
            copied = json.loads(json.dumps(dict(self.endpoint), allow_nan=False))
        except (TypeError, ValueError):
            raise ValueError("Conversation endpoint requires JSON values") from None
        object.__setattr__(self, "endpoint", _freeze(copied))


def endpoint_dict(conversation: ConversationRef) -> dict:
    """Thaw an immutable reference to a detached JSON endpoint for Store serialization."""
    def thaw(value):
        if isinstance(value, Mapping):
            return {key: thaw(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return [thaw(item) for item in value]
        return value

    return thaw(conversation.endpoint)


@dataclass(frozen=True)
class ChannelCapabilities:
    """Supported behavior and explicit fallback for unsupported conversation threads."""

    threads: bool = False
    inbound_text: bool = True
    outbound_text: bool = True
    actions: bool = False
    delivery_acknowledgement: bool = False
    message_editing: bool = False
    audio: bool = False
    deep_links: bool = False
    notifications: bool = False
    accessibility: bool = True
    fallback: str = "in_chat_mode_commands"


@dataclass(frozen=True)
class IncomingUpdate:
    """One decoded inbound event; ids stay in the channel's native form."""

    update_id: str | int
    kind: Literal["message", "callback_query"]
    chat_id: Recipient
    conversation: ConversationRef | None
    text: str | None = None
    message_id: int | None = None
    data: str | None = None
    callback_id: str | None = None


class ConversationUnavailableError(RuntimeError):
    """Delivery needs an application-level conversation repair; never resend unaddressed."""

    def __init__(self, conversation: ConversationRef):
        super().__init__("Conversation is unavailable")
        self.conversation = conversation


class MessageChannel(Protocol):
    channel_id: str
    # How participant-facing copy names this app, e.g. "Telegram is connected".
    display_name: str
    capabilities: ChannelCapabilities

    # Lifecycle (ADR 0005). `ready`: can deliver now; while False, proactive messages wait
    # pending. `connect_link`: where the dashboard sends a participant before Pairing, or None.
    @property
    def ready(self) -> bool: ...

    @property
    def connect_link(self) -> str | None: ...

    async def start(self) -> None:
        """Connect or initialize; may raise, and the caller bounds and judges it."""
        ...

    async def close(self) -> None:
        """Stop taking events, let in-flight work finish (bounded), then disconnect."""
        ...

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
        conversation: ConversationRef | None = None,
    ) -> int | None: ...

    async def edit_message_buttons(
        self,
        chat_id: str | int,
        message_id: int,
        *,
        buttons: list[list[dict[str, str]]] | None = None,
        conversation: ConversationRef | None = None,
    ) -> None: ...

    async def create_conversation(self, chat_id: str | int, name: str) -> ConversationRef: ...

    async def close_conversation(
        self, chat_id: str | int, conversation: ConversationRef
    ) -> None: ...

    async def conversation_link(self, conversation: ConversationRef | None) -> str | None: ...

    async def recipient_for(self, user: dict) -> str | int | None: ...

    async def recipient_matches(
        self, conversation: ConversationRef, recipient: str | int
    ) -> bool: ...
