"""Tool Context: the runtime dependencies injected into every Tool call.

The model never sees these values. The Mode runtime builds one per Turn and the agent framework
passes it to each Tool as `ctx.deps`.
"""

from dataclasses import dataclass, field
from typing import Any

from src.channels.base import ConversationRef, MessageChannel, Recipient
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler
from src.utils import Clock, default_clock


@dataclass
class ToolContext:
    """Per-Turn dependencies injected into every Tool call."""

    store: MemoryStore
    scheduler: ReminderScheduler
    channel: MessageChannel
    user: dict
    session_id: str
    chat_id: Recipient
    timezone: str
    turn_id: str
    clock: Clock = default_clock
    conversation: ConversationRef | None = None
    entered_by: str = "command"
    mode_id: str = "daily"
    mode_registry: Any = None
    handoff_id: str | None = None
    handoff_claim_token: str | None = None
    handoff_cancel_targets: dict[str, list[str]] = field(default_factory=dict)
