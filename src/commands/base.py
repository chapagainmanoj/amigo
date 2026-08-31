"""Shared command context and errors."""

from dataclasses import dataclass
from typing import Literal


class IdempotencyConflictError(ValueError):
    """Raised when one idempotency key is reused for different input."""


class StaleVersionError(ValueError):
    """Raised when a command targets an aggregate version that is no longer current."""


class InvalidTransitionError(ValueError):
    """Raised when a terminal aggregate is asked to transition to another outcome."""


@dataclass(frozen=True)
class CommandContext:
    """Identity and replay metadata injected by a trusted adapter."""

    actor_user_id: str
    surface: Literal["telegram", "dashboard"]
    idempotency_key: str
