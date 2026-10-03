"""The Mode registry: deny-by-default lookup of registered Mode Definitions."""

from collections.abc import Iterable, Iterator
from pathlib import Path

from src.agent.modes import PLACEHOLDER_FACTS, ModeDefinition, UnknownModeError
from src.evaluation.model_policy import require_evaluated_fallback


class ModeRegistry:
    """Holds every registered Mode. Unknown ids are refused, never substituted."""

    def __init__(self, modes: Iterable[ModeDefinition] = ()):
        self._modes: dict[str, ModeDefinition] = {}
        for mode in modes:
            _register(self._modes, mode)

    async def register(self, mode: ModeDefinition) -> None:
        """Register a Mode after validating every startup invariant."""
        _register(self._modes, mode)

    async def get(self, mode_id: str) -> ModeDefinition:
        try:
            return self._modes[mode_id]
        except KeyError:
            raise UnknownModeError(mode_id) from None

    async def live(self) -> list[ModeDefinition]:
        return [mode for mode in self._modes.values() if mode.status == "live"]

    def __getitem__(self, mode_id: str) -> ModeDefinition:
        """Resolve a Mode for synchronous configuration consumers such as schema capture."""
        try:
            return self._modes[mode_id]
        except KeyError:
            raise UnknownModeError(mode_id) from None

    def __iter__(self) -> Iterator[ModeDefinition]:
        return iter(self._modes.values())


def _register(modes: dict[str, ModeDefinition], mode: ModeDefinition) -> None:
    """Constructor helper; ``__init__`` cannot await the public async registration method."""
    if mode.id in modes:
        raise ValueError(f"Mode {mode.id!r} is already registered")
    if mode.status == "live":
        _require_renderable(mode)
        root = Path(__file__).resolve().parents[2]
        if not mode.eval_suite or not (root / mode.eval_suite).is_file():
            raise ValueError(f"live Mode {mode.id!r} must declare an existing evaluation suite")
        require_evaluated_fallback(mode, root)
    _require_unique_tool_names(mode)
    _require_known_tool_order(mode)
    modes[mode.id] = mode


def _require_renderable(mode: ModeDefinition) -> None:
    """A live Mode whose instructions cannot render fails here, not on a participant's Turn."""
    try:
        rendered = mode.instructions(PLACEHOLDER_FACTS)
    except Exception as error:
        raise ValueError(f"Mode {mode.id!r} instructions failed to render: {error}") from error
    if not isinstance(rendered, str) or not rendered.strip():
        raise ValueError(f"Mode {mode.id!r} instructions rendered empty")


def _require_known_tool_order(mode: ModeDefinition) -> None:
    """Every name in a declared presentation order must be a Tool the Mode actually has."""
    if not mode.tool_order:
        return
    if len(set(mode.tool_order)) != len(mode.tool_order):
        raise ValueError(f"Mode {mode.id!r} names a Tool more than once in its tool order")
    known: set[str] = set()
    for toolset in mode.toolsets:
        tools = getattr(toolset, "tools", None)
        if tools is None:
            raise ValueError(
                f"Mode {mode.id!r} declares a tool order over a Toolset that cannot list its Tools"
            )
        known.update(tools)
    unknown = sorted(set(mode.tool_order) - known)
    if unknown:
        raise ValueError(f"Mode {mode.id!r} orders Tools it does not have: {unknown}")


def _require_unique_tool_names(mode: ModeDefinition) -> None:
    """Two Toolsets offering the same Tool name would fail on a participant's first Turn."""
    seen: set[str] = set()
    for toolset in mode.toolsets:
        names = set(getattr(toolset, "tools", None) or ())
        clash = sorted(seen & names)
        if clash:
            raise ValueError(f"Mode {mode.id!r} has Tools in more than one Toolset: {clash}")
        seen |= names
