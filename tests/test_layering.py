"""Import direction between code layers (cosmic-python skill, references/amigo-layer-map.md).

This module is the enforced layer map. Classify every new ``src`` module here by role, not
folder; shrink ``KNOWN_EDGES`` as edges are fixed, never grow it without a review-queue entry.
Imports under ``if TYPE_CHECKING:`` carry no runtime dependency and are not counted.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"

DOMAIN = "domain"
CONFIG = "config"
ADAPTER = "adapter"
SERVICE = "service"
ENTRYPOINT = "entrypoint"

ALLOWED: dict[str, frozenset[str]] = {
    DOMAIN: frozenset({DOMAIN}),
    CONFIG: frozenset({CONFIG, DOMAIN}),
    ADAPTER: frozenset({ADAPTER, CONFIG, DOMAIN}),
    SERVICE: frozenset({SERVICE, ADAPTER, CONFIG, DOMAIN}),
    ENTRYPOINT: frozenset({ENTRYPOINT, SERVICE, ADAPTER, CONFIG, DOMAIN}),
}

# Longest dotted prefix wins. Package entries cover their submodules.
LAYERS: dict[str, str] = {
    # Domain: rules, declarations, value types. No I/O, no settings, no Store.
    "activation": DOMAIN,
    "agent.modes": DOMAIN,
    "agent.prompts": DOMAIN,
    "agent.safety": DOMAIN,
    "bot.keyboards": DOMAIN,  # pure button declarations; channels render them
    "channels.base": DOMAIN,
    "coaching_templates": DOMAIN,
    "commands.base": DOMAIN,
    "dashboard_snapshot": DOMAIN,
    "evaluation.meaning": DOMAIN,
    "schema": DOMAIN,
    "time_resolution": DOMAIN,
    "utils": DOMAIN,
    "wellbeing": DOMAIN,
    "workflows": DOMAIN,
    # Config: settings, model-route parsing, fail-closed validation.
    "config": CONFIG,
    "model_routing": CONFIG,
    "runtime_config": CONFIG,
    # Adapters: database, chat providers, model providers, measurement sinks.
    "agent.claude_cli_model": ADAPTER,
    "channels": ADAPTER,
    "db": ADAPTER,
    "memory": ADAPTER,
    "model_usage": ADAPTER,
    "observability": ADAPTER,
    "telemetry": ADAPTER,
    # Services: use cases, application commands, access/readiness policies, Mode catalogue.
    "access": SERVICE,
    "agent": SERVICE,
    "bot.update_claims": SERVICE,  # per-participant Turn serialization, any channel
    "channels.registry": SERVICE,  # picks the proactive delivery channel by access rule
    "coaching": SERVICE,
    "commands": SERVICE,
    "conversations": SERVICE,
    "evaluation": SERVICE,
    "handoffs": SERVICE,
    "maintenance": SERVICE,
    "memory_service": SERVICE,
    "mode_readiness": SERVICE,
    "mode_suggestions": SERVICE,
    "reliability": SERVICE,  # awaits the Store and logs; readiness use case for main
    "scheduler": SERVICE,
    "tools": SERVICE,
    "turns": SERVICE,
    # Entrypoints: parse, call one service, format.
    "__main__": ENTRYPOINT,
    "api": ENTRYPOINT,
    "auth": ENTRYPOINT,
    "bot": ENTRYPOINT,
    "cli": ENTRYPOINT,
    "main": ENTRYPOINT,
    "startup": ENTRYPOINT,
}

# (importer, imported) pairs that break ALLOWED today. Fix, then delete the entry.
KNOWN_EDGES: frozenset[tuple[str, str]] = frozenset(
    {
        # Fail-closed production gate (privacy decision 04): MODE_MODELS and a non-Gemini
        # default need current per-Mode evaluation evidence before any side effect starts.
        # Kept in validate_runtime_configuration so one call stays the whole gate.
        ("runtime_config", "agent.catalogue"),
        ("runtime_config", "evaluation.model_policy"),
    }
)


def _module_name(path: Path) -> str:
    parts = path.relative_to(SRC).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _layer(module: str) -> str | None:
    parts = module.split(".")
    for end in range(len(parts), 0, -1):
        layer = LAYERS.get(".".join(parts[:end]))
        if layer:
            return layer
    return None


def _modules() -> list[tuple[str, Path]]:
    return [
        (_module_name(path), path)
        for path in sorted(SRC.rglob("*.py"))
        if _module_name(path)  # src/__init__.py
    ]


def _is_type_checking(node: ast.AST) -> bool:
    return isinstance(node, ast.If) and (
        (isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING")
        or (isinstance(node.test, ast.Attribute) and node.test.attr == "TYPE_CHECKING")
    )


def _runtime_nodes(tree: ast.AST):
    """Walk the tree, skipping `if TYPE_CHECKING:` bodies (no runtime dependency)."""
    stack = [tree]
    while stack:
        node = stack.pop()
        yield node
        if _is_type_checking(node):
            stack.extend(node.orelse)
            continue
        stack.extend(ast.iter_child_nodes(node))


def _imports(path: Path, source: str | None = None) -> set[str]:
    """Runtime ``src`` imports, as dotted names under ``src``.

    ``from src.pkg import name`` counts as ``pkg.name`` when ``name`` is a submodule, so a stricter
    submodule layer is not hidden behind its package's. Relative imports resolve against ``path``.
    """
    package = _module_name(path).split(".") if path.name == "__init__.py" else (
        _module_name(path).split(".")[:-1]
    )
    found = set()
    for node in _runtime_nodes(ast.parse(source if source is not None else path.read_text())):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
                module = ".".join([*base, *([node.module] if node.module else [])])
            elif node.module == "src" or (node.module or "").startswith("src."):
                module = node.module.removeprefix("src").lstrip(".")
            else:
                continue
            for alias in node.names:
                candidate = f"{module}.{alias.name}" if module else alias.name
                found.add(candidate if _is_module(candidate) else module)
        elif isinstance(node, ast.Import):
            names = (alias.name for alias in node.names)
            found.update(n.removeprefix("src.") for n in names if n.startswith("src."))
    found.discard("")
    return found


def _is_module(dotted: str) -> bool:
    path = SRC.joinpath(*dotted.split("."))
    return path.with_suffix(".py").exists() or (path / "__init__.py").exists()


def _violations() -> set[tuple[str, str]]:
    bad = set()
    for module, path in _modules():
        importer = _layer(module)
        for imported in _imports(path):
            target = _layer(imported)
            if importer and target and target not in ALLOWED[importer]:
                bad.add((module, imported))
    return bad


def test_every_module_has_a_layer():
    unclassified = [module for module, _ in _modules() if _layer(module) is None]
    assert not unclassified, f"classify in tests/test_layering.py LAYERS: {unclassified}"


def test_imports_point_inward():
    new = sorted(_violations() - KNOWN_EDGES)
    assert not new, f"layer violations (cosmic-python:AP-OUTWARD-IMPORT): {new}"


def test_import_forms_are_resolved():
    """Package-relative, ``from src import x`` and ``from src.pkg import submodule`` all count."""
    source = (
        "from src import access\n"
        "from src.channels import registry\n"
        "from . import base\n"
        "from .registry import ChannelRegistry\n"
        "from src.memory.store import MemoryStore\n"
        "if TYPE_CHECKING:\n"
        "    from src.turns import SessionTurnOrchestrator\n"
    )
    assert _imports(SRC / "channels" / "telegram.py", source) == {
        "access", "channels.registry", "channels.base", "memory.store"
    }


def test_known_edges_are_still_real():
    fixed = sorted(KNOWN_EDGES - _violations())
    assert not fixed, f"remove fixed edges from KNOWN_EDGES: {fixed}"
