"""Replaceable policies. Changing who can use a Mode, or how a Turn picks one, is a policy swap."""

from typing import Protocol

from src.agent.modes import ModeDefinition
from src.tools.context import ToolContext


class RoutingPolicy(Protocol):
    async def select(self, context: ToolContext, requested_mode: str | None) -> str:
        """Return the id of the Mode that should handle this Turn."""


class EntitlementPolicy(Protocol):
    async def allows(self, context: ToolContext, mode: ModeDefinition) -> bool:
        """Whether this participant may use this Mode."""


class ExplicitThenDefault:
    """An explicitly requested Mode wins; otherwise the default Mode handles the Turn."""

    def __init__(self, default: str = "daily"):
        self.default = default

    async def select(self, context: ToolContext, requested_mode: str | None) -> str:
        return self.default if requested_mode is None else requested_mode


class ActivatedParticipants:
    """Every activated participant holds the "activated" entitlement and nothing more."""

    async def allows(self, context: ToolContext, mode: ModeDefinition) -> bool:
        return mode.entitlement == "activated"
