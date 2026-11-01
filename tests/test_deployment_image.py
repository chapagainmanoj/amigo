"""The production image carries every file startup reads (Dockerfile COPY set)."""

import re
from pathlib import Path

from src.agent.catalogue import build_registry
from src.evaluation.gate_a import invalidating_inputs

ROOT = Path(__file__).resolve().parents[1]


def _copied() -> list[str]:
    """Repo-relative sources of every ``COPY <src> <dest>`` in the Dockerfile."""
    sources = []
    for line in (ROOT / "Dockerfile").read_text().splitlines():
        match = re.match(r"\s*COPY\s+(?!--)(.+)\s+\S+\s*$", line)
        if match:
            sources.extend(match.group(1).split())
    return [source.rstrip("/") for source in sources]


def _in_image(relative: str, copied: list[str]) -> bool:
    return any(relative == source or relative.startswith(f"{source}/") for source in copied)


def test_every_gate_a_fingerprint_input_ships_in_the_image():
    """Evaluated model routes recompute this fingerprint at production startup.

    A file missing from the image changes the fingerprint (or fails to read), so a route with
    valid evidence could never start.
    """
    copied = _copied()
    inputs = {
        str(path.relative_to(ROOT))
        for mode in build_registry()
        for path in invalidating_inputs(ROOT, mode_definition=mode)
    }
    missing = sorted(path for path in inputs if not _in_image(path, copied))
    assert not missing, f"add to the Dockerfile COPY set: {missing}"
