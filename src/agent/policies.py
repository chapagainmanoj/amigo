"""Replaceable policies. Changing who can use a Mode, or how a Turn picks one, is a policy swap."""

from typing import Protocol

from src.agent.modes import ModeDefinition, ModeUnavailableError
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


class TieredEntitlements:
    """Activated Modes for everyone; full-access Modes for allowlisted chats or grant holders."""

    async def allows(self, context: ToolContext, mode: ModeDefinition) -> bool:
        from src.access import entitled

        return await entitled(context.store, context.user, mode)


async def admit(
    context: ToolContext, mode: ModeDefinition, entitlements: EntitlementPolicy | None = None
) -> None:
    """Raise ModeUnavailableError unless this participant may run a Turn in this Mode now.

    The one admission check: Turns, the dashboard, Coach buttons and the CLI all use it.
    """
    if mode.status != "live":
        raise ModeUnavailableError(mode.id, mode.status, f"{mode.name} isn't available yet.")
    if not await (entitlements or TieredEntitlements()).allows(context, mode):
        raise ModeUnavailableError(
            mode.id, "not entitled", f"{mode.name} isn't available on your account."
        )
    if mode.entry_guard is not None:
        refusal = await mode.entry_guard(context)
        if refusal:
            raise ModeUnavailableError(mode.id, "readiness", refusal)
