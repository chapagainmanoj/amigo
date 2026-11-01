"""A live fallback must point to a complete, passing declared run for that Mode/model."""

import hashlib
import json
from pathlib import Path

from src.agent.modes import DAILY_MODE_ID


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
        "entry_guard": (
            f"{mode.entry_guard.__module__}.{mode.entry_guard.__qualname__}"
            if mode.entry_guard is not None else None
        ),
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
        if inputs.get("mode_id", DAILY_MODE_ID) != mode.id:
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
        elif mode.id != DAILY_MODE_ID:
            raise ValueError("fallback evidence must pin its Mode instructions")
        # Recompute every case score and aggregate, never trust a manifest's passed flag.
        # Supplying the Mode avoids registration recursion while validating startup invariants.
        from src.evaluation.gate_a_evidence import check_evidence

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


def require_evaluated_model(mode, model: str, root: Path) -> None:
    """Validate a Mode/model allowlist artifact, without certifying production Gate A.

    Reuse the full run's scoring and trace validator. Its Gemini-only certification rejection
    is the sole deliberately excluded condition here; the Gate A entry point still rejects
    that same artifact. All identity, currency and content hashes are mandatory independently.
    """
    from src.agent.modes import PLACEHOLDER_FACTS
    from src.evaluation.gate_a import canonical_hash, is_gemini_model, tool_schema
    from src.model_routing import normalize_model

    try:
        model = normalize_model(model)
        manifest = json.loads((root / "evals/model-evidence.json").read_text())
        entry = next(
            entry
            for entry in manifest["entries"]
            if entry["mode_id"] == mode.id and normalize_model(entry["model"]) == model
        )
        artifact_path = (root / entry["artifact"]).resolve()
        if not artifact_path.is_relative_to(root.resolve()):
            raise ValueError("Model evidence must be a repository artifact")
        artifact = artifact_path.read_bytes()
        if hashlib.sha256(artifact).hexdigest() != entry["sha256"]:
            raise ValueError("Model artifact hash mismatch")
        evidence = json.loads(artifact)
        inputs = evidence["release_inputs"]
        _require_model_review(entry, evidence)
        if (
            inputs.get("mode_id", DAILY_MODE_ID) != mode.id
            or normalize_model(inputs["model"]) != model
            or normalize_model(inputs["provider_model"]) != model
            or inputs.get("fallback_currency") != fallback_currency(mode, root)
            or inputs.get("model_settings") != (mode.model.settings or {})
            or inputs.get("tool_schema_sha256") != canonical_hash(tool_schema(mode_definition=mode))
            or inputs.get("mode_instructions_sha256")
            != canonical_hash(mode.instructions(PLACEHOLDER_FACTS))
        ):
            raise ValueError("Model evidence identity or execution inputs are stale")
        from src.evaluation.gate_a_evidence import check_evidence

        errors = check_evidence(
            evidence,
            revision=inputs["git_revision"],
            root=root,
            suite_path=root / mode.eval_suite,
            mode_id=mode.id,
            mode_definition=mode,
            model_name=model,
            _historical_baseline=True,
        )
        if not is_gemini_model(model):
            excluded = {"Non-Gemini development evidence cannot certify Gate A"}
            if evidence.get("purpose") == "development_eval":
                excluded.add("historical baseline must be a declared full-run artifact")
            errors = [error for error in errors if error not in excluded]
        if errors:
            raise ValueError("Model evidence failed validation")
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        raise ValueError(
            f"Mode {mode.id!r} model has no current passing evaluation evidence"
        ) from None


def _require_model_review(entry: dict, evidence: dict) -> None:
    """The operator review binds subjective evaluation to the exact retained artifact bytes."""
    import re
    from datetime import UTC, datetime

    from src.utils import utc_now

    review = entry["human_review"]
    reviewed = datetime.fromisoformat(review["reviewed_at"])
    completed = datetime.fromisoformat(evidence["completed_at"])
    current = utc_now()
    current = current.replace(tzinfo=UTC) if current.tzinfo is None else current.astimezone(UTC)
    if (
        review.get("status") != "approved"
        or review.get("artifact_sha256") != entry["sha256"]
        or review.get("tone_reviewed") is not True
        or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,63}", review.get("reviewer", ""))
        or not isinstance(review.get("notes"), str)
        or not review["notes"].strip()
        or reviewed.tzinfo is None
        or completed.tzinfo is None
        or not completed <= reviewed <= current
    ):
        raise ValueError("Model evidence requires artifact-bound human review")
