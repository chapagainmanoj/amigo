"""Tool Context: the runtime dependencies injected into every Tool call.

The model never sees these values. The Mode runtime builds one per Turn and the agent framework
passes it to each Tool as `ctx.deps`.
"""

from dataclasses import dataclass

from src.channels.base import MessageChannel
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
    chat_id: int
    timezone: str
    turn_id: str
    clock: Clock = default_clock
