"""Mode Definitions: what a Mode is allowed to do, declared as data.

A Mode is a temporary, participant-entered interaction contract (see CONTEXT.md). Its definition
declares purpose, instructions, Toolsets, Turn Context providers, entitlement, model, handoff
targets, and evaluation suite. Definitions carry no side effects; the Mode runtime executes them.
"""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai.toolsets import AbstractToolset

from src.tools.context import ToolContext

ModeStatus = Literal["live", "planned", "disabled"]
ContextProvider = Callable[[ToolContext], Awaitable[str | None]]

_MODE_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


@dataclass(frozen=True)
class TurnFacts:
    """Participant facts a Mode's instructions may interpolate, built without any I/O."""

    participant_name: str
    local_time: str


# Neutral facts for rendering a Mode's instructions without any participant data.
PLACEHOLDER_FACTS = TurnFacts(
    participant_name="participant", local_time="2000-01-01 00:00 Saturday"
)


@dataclass(frozen=True)
class ModelPolicy:
    """Evaluated model choices; None for primary means the configured default."""

    primary: str | None = None
    fallback: str | None = None
    settings: dict[str, Any] | None = None

    def __post_init__(self):
        for reference in (self.primary, self.fallback):
            if reference is not None and (
                not isinstance(reference, str) or not reference or reference != reference.strip()
            ):
                raise ValueError("model references must be nonempty model identifiers")
        if self.fallback is not None and self.fallback == self.primary:
            raise ValueError("fallback must name a different model")


@dataclass(frozen=True)
class ModeDefinition:
    """One registered Mode. Policy is a value here, so changing policy is not a refactor."""

    id: str
    name: str
    purpose: str
    status: ModeStatus
    instructions: Callable[[TurnFacts], str] | None = None
    toolsets: tuple[AbstractToolset[ToolContext], ...] = ()
    # The order Tools are presented to the model. Models are sensitive to it, and Toolsets are
    # grouped by domain rather than by presentation, so a Mode may pin it. Unlisted Tools follow
    # in Toolset order.
    tool_order: tuple[str, ...] = ()
    context: tuple[ContextProvider, ...] = ()
    # Entitlement the participant must hold. Every activated participant holds "activated".
    entitlement: str = "activated"
    model: ModelPolicy = ModelPolicy()
    handoffs: tuple[str, ...] = ()
    eval_suite: str | None = None
    invalidating_inputs: tuple[str, ...] = ()

    def __post_init__(self):
        if not _MODE_ID.match(self.id):
            raise ValueError(f"invalid Mode id {self.id!r}")
        if self.status == "live" and self.instructions is None:
            raise ValueError(f"live Mode {self.id!r} must declare instructions")


class ModeUnavailableError(Exception):
    """A Turn asked for a Mode the runtime must refuse. Raised before anything is written."""

    def __init__(self, mode_id: str, reason: str, participant_message: str):
        super().__init__(f"Mode {mode_id!r} unavailable: {reason}")
        self.mode_id = mode_id
        self.reason = reason
        self.participant_message = participant_message


class UnknownModeError(ModeUnavailableError):
    """No Mode is registered under the requested id. Never falls back to another Mode."""

    def __init__(self, mode_id: str):
        super().__init__(
            mode_id,
            "unknown",
            "That mode doesn't exist.",
        )
