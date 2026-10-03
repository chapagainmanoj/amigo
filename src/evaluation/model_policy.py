"""A live fallback must point to a complete, passing declared run for that Mode/model."""

import hashlib
import json
from pathlib import Path


def fallback_currency(mode, root: Path) -> dict:
    """Current evaluated behavior, excluding the declaration of the fallback itself.

    Catalogue/manifest edits are necessary to activate an already evaluated fallback. Pin the
    evaluated Mode's instructions, Tool order/schema, and ordered context providers separately;
    every execution source and SDK version still invalidates its fallback evidence.
    """
    from src.agent.modes import PLACEHOLDER_FACTS
    from src.evaluation.gate_a import (
        canonical_hash,
        dependency_versions,
        file_set_hash,
        invalidating_inputs,
        tool_schema,
    )

    excluded = {root / "src/agent/catalogue.py", root / "evals/fallback-evidence.json"}
    return {
        "instructions_sha256": canonical_hash(mode.instructions(PLACEHOLDER_FACTS)),
        "tool_schema_sha256": canonical_hash(tool_schema(mode_definition=mode)),
        "tool_order": list(mode.tool_order),
        "context_providers": [
            f"{provider.__module__}.{provider.__qualname__}" for provider in mode.context
        ],
        "source_sha256": file_set_hash(
            [path for path in invalidating_inputs(root, mode) if path not in excluded], root
        ),
        "dependency_versions": dependency_versions(),
    }


def require_evaluated_fallback(mode, root: Path) -> None:
    if mode.model.fallback is None:
        return
    try:
        manifest = json.loads((root / "evals/fallback-evidence.json").read_text())
        entry = next(
            entry
            for entry in manifest["entries"]
            if entry["mode_id"] == mode.id and entry["model"] == mode.model.fallback
        )
        artifact_path = (root / entry["artifact"]).resolve()
        if not artifact_path.is_relative_to(root.resolve()):
            raise ValueError("fallback evidence must be a repository artifact")
        artifact = artifact_path.read_bytes()
        if hashlib.sha256(artifact).hexdigest() != entry["sha256"]:
            raise ValueError("fallback artifact hash does not match")
        evidence = json.loads(artifact)
        inputs = evidence["release_inputs"]
        if inputs.get("fallback_currency") != fallback_currency(mode, root):
            raise ValueError("fallback evidence execution sources or SDK versions are stale")
        if inputs.get("mode_id", "daily") != mode.id:
            raise ValueError("fallback evidence is for another Mode")
        candidate = mode.model.fallback.removeprefix("google:")
        if inputs["model"].removeprefix("google:") != candidate:
            raise ValueError("fallback evidence is for another model")
        from src.agent.modes import PLACEHOLDER_FACTS
        from src.evaluation.gate_a import canonical_hash, tool_schema

        if inputs["tool_schema_sha256"] != canonical_hash(tool_schema(mode_definition=mode)):
            raise ValueError("fallback evidence Tool schemas are stale")
        if inputs["model_settings"] != (mode.model.settings or {}):
            raise ValueError("fallback evidence model settings are stale")
        if "mode_instructions_sha256" in inputs:
            if inputs["mode_instructions_sha256"] != canonical_hash(
                mode.instructions(PLACEHOLDER_FACTS)
            ):
                raise ValueError("fallback evidence Mode instructions are stale")
        elif mode.id != "daily":
            raise ValueError("fallback evidence must pin its Mode instructions")
        # Recompute every case score and aggregate, never trust a manifest's passed flag.
        # Supplying the Mode avoids registration recursion while validating startup invariants.
        from scripts.check_gate_a_evidence import check_evidence

        errors = check_evidence(
            evidence,
            revision=inputs["git_revision"],
            root=root,
            suite_path=root / mode.eval_suite,
            mode_id=mode.id,
            mode_definition=mode,
            _historical_baseline=True,
        )
        if errors:
            raise ValueError("; ".join(errors))
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as error:
        raise ValueError(
            f"live Mode {mode.id!r} fallback has no passing Gate A evidence"
        ) from error
