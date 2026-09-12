"""Fail-closed validation for the dated Internal Preflight release-evidence manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

REQUIRED_CHECKS = {
    "backend_ci", "frontend_ci", "clean_migrations", "model_evaluation",
    "tenant_isolation", "fail_closed_configuration", "telegram_replay",
    "ambiguous_time", "scheduler_restart", "liveness", "readiness",
    "application_errors", "reminder_delivery", "reminder_lateness",
    "render_owner", "webhook_owner", "separate_staging_resources",
    "public_urls_and_copy", "independent_security_review",
}
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ARTIFACT_SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
ACTOR_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._@-]{2,127}$")
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")


def _required_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not value.strip().startswith("<")


def _actor_id(value: object, label: str, errors: list[str]) -> str | None:
    if not _required_text(value):
        return None
    normalized = value.strip().casefold()
    if value != normalized or not ACTOR_ID_PATTERN.fullmatch(normalized):
        errors.append(f"{label} must be a canonical lowercase stable actor ID")
    return normalized


def _run_id(value: object, label: str, errors: list[str]) -> str | None:
    if not _required_text(value):
        return None
    normalized = value.strip().casefold()
    if value != normalized or not RUN_ID_PATTERN.fullmatch(normalized):
        errors.append(f"{label} must be a canonical lowercase stable run ID")
    return normalized


def _parse_timestamp(value: object, label: str, errors: list[str]) -> datetime | None:
    if not _required_text(value) or not TIMESTAMP_PATTERN.fullmatch(value):
        errors.append(f"{label} must be a real UTC timestamp ending in Z")
        return None
    try:
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00").astimezone(UTC)
    except ValueError:
        errors.append(f"{label} must be a real UTC timestamp ending in Z")
        return None


def _validate_evidence(
    value: object, label: str, evidence_root: Path | None, errors: list[str]
) -> str | None:
    if not isinstance(value, dict):
        errors.append(f"{label} must contain path and sha256")
        return None
    path_value = value.get("path")
    digest = value.get("sha256")
    if not _required_text(path_value):
        errors.append(f"{label}.path is required")
        return None
    relative = PurePosixPath(path_value)
    if relative.is_absolute() or ".." in relative.parts:
        errors.append(f"{label}.path must stay within the manifest directory")
        return None
    if not isinstance(digest, str) or not ARTIFACT_SHA_PATTERN.fullmatch(digest):
        errors.append(f"{label}.sha256 must be a lowercase SHA-256 digest")
        return None
    if evidence_root is None:
        errors.append(f"{label} cannot be verified without an evidence root")
        return digest
    root = evidence_root.resolve()
    artifact = (root / Path(*relative.parts)).resolve()
    if artifact != root and root not in artifact.parents:
        errors.append(f"{label}.path escapes the manifest directory")
        return digest
    if not artifact.is_file():
        errors.append(f"{label}.path does not exist: {path_value}")
        return digest
    actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if actual != digest:
        errors.append(f"{label}.sha256 does not match the artifact")
    return digest


def _validate_metadata(
    item: dict,
    label: str,
    *,
    revision: object,
    environment: object,
    deployment_id: object,
    implementer: object,
    started_at: datetime | None,
    ended_at: datetime | None,
    evidence_root: Path | None,
    errors: list[str],
    timestamp_field: str = "observed_at",
    require_status: bool = True,
) -> tuple[datetime | None, str | None]:
    if require_status and item.get("status") != "pass":
        errors.append(f"{label} is not passing")
    for field in (
        "producer", "reviewer", timestamp_field, "revision", "environment", "deployment_id"
    ):
        if not _required_text(item.get(field)):
            errors.append(f"{label}.{field} is required")
    producer = _actor_id(item.get("producer"), f"{label}.producer", errors)
    reviewer = _actor_id(item.get("reviewer"), f"{label}.reviewer", errors)
    if producer == reviewer:
        errors.append(f"{label} producer and reviewer must be different people")
    if reviewer == implementer:
        errors.append(f"{label} cannot be reviewed by the release implementer")
    if item.get("revision") != revision:
        errors.append(f"{label}.revision does not match the release")
    if item.get("environment") != environment:
        errors.append(f"{label}.environment does not match the release")
    if item.get("deployment_id") != deployment_id:
        errors.append(f"{label}.deployment_id does not match the release")
    observed_at = _parse_timestamp(item.get(timestamp_field), f"{label}.{timestamp_field}", errors)
    if observed_at and started_at and observed_at < started_at:
        errors.append(f"{label}.{timestamp_field} predates evidence collection")
    if observed_at and ended_at and observed_at > ended_at:
        errors.append(f"{label}.{timestamp_field} is after evidence collection ended")
    digest = _validate_evidence(item.get("evidence"), f"{label}.evidence", evidence_root, errors)
    return observed_at, digest


def template_manifest() -> dict:
    """Return a complete-shape manifest whose missing values intentionally cannot pass."""
    metadata = {
        "status": "missing", "producer": "<evidence producer>",
        "reviewer": "<independent reviewer>", "observed_at": "<UTC timestamp>",
        "revision": "<full Git SHA>", "environment": "staging",
        "deployment_id": "<Render deployment ID>",
        "evidence": {"path": "<relative artifact path>", "sha256": "<artifact SHA-256>"},
    }
    trial = {
        **metadata, "run_id": "<unique run ID>", "previous_trial_sha256": None,
        "dashboard_account": False, "pairing": False, "task": False,
        "reminder_delivered": False, "done": False, "dashboard_synchronized": False,
        "no_duplicate": False, "no_cross_participant_effect": False,
        "no_lost_delivery": False,
    }
    return {
        "schema_version": "amigo-internal-preflight-v1",
        "release": {
            "revision": "<full Git SHA>", "environment": "staging",
            "deployment_id": "<Render deployment ID>", "started_at": "<UTC timestamp>",
            "ended_at": "<UTC timestamp>", "operator": "<operator>",
            "implementer": "<release implementer>",
        },
        "topology": {
            "render_backend_instances": None, "scheduler_owners": None,
            "webhook_destinations": None, "fly_active": None, "always_on": None,
            "telegram_resource_separate": None, "supabase_resource_separate": None,
            "dashboard_resource_separate": None, "model_resource_separate": None,
        },
        "checks": [{"id": check_id, **metadata} for check_id in sorted(REQUIRED_CHECKS)],
        "core_loop_trials": [{"sequence": sequence, **trial} for sequence in (1, 2, 3)],
        "open_findings": {
            "critical": None, "gate_a_high": None,
            **{key: value for key, value in metadata.items() if key != "status"},
        },
        "founder_decision": {
            "decision": "missing", "founder": "<founder>",
            "reviewer": "<decision witness>", "recorded_at": "<UTC timestamp>",
            "revision": "<full Git SHA>", "environment": "staging",
            "deployment_id": "<Render deployment ID>",
            "evidence": {"path": "<decision artifact>", "sha256": "<artifact SHA-256>"},
        },
    }


def validate_manifest(
    manifest: dict, *, evidence_root: Path | None = None, now: datetime | None = None
) -> list[str]:
    """Return every reason the manifest cannot prove Internal Preflight passage."""
    errors: list[str] = []
    if manifest.get("schema_version") != "amigo-internal-preflight-v1":
        errors.append("schema_version must be amigo-internal-preflight-v1")
    release = manifest.get("release") or {}
    revision = release.get("revision")
    environment = release.get("environment")
    deployment_id = release.get("deployment_id")
    implementer = release.get("implementer")
    if not isinstance(revision, str) or not SHA_PATTERN.fullmatch(revision):
        errors.append("release.revision must be a full lowercase Git commit SHA")
    if environment != "staging":
        errors.append("release.environment must be staging")
    for field in ("deployment_id", "operator", "implementer"):
        if not _required_text(release.get(field)):
            errors.append(f"release.{field} is required")
    _actor_id(release.get("operator"), "release.operator", errors)
    implementer = _actor_id(implementer, "release.implementer", errors)
    started_at = _parse_timestamp(release.get("started_at"), "release.started_at", errors)
    ended_at = _parse_timestamp(release.get("ended_at"), "release.ended_at", errors)
    if started_at and ended_at and ended_at <= started_at:
        errors.append("release.ended_at must be after release.started_at")
    now_utc = (now or datetime.now(UTC)).astimezone(UTC)
    if started_at and started_at > now_utc:
        errors.append("release.started_at cannot be in the future")
    if ended_at and ended_at > now_utc:
        errors.append("release.ended_at cannot be in the future")

    facts = manifest.get("topology") or {}
    expected_facts = {
        "render_backend_instances": 1, "scheduler_owners": 1, "webhook_destinations": 1,
        "fly_active": False, "always_on": True, "telegram_resource_separate": True,
        "supabase_resource_separate": True, "dashboard_resource_separate": True,
        "model_resource_separate": True,
    }
    for field, expected in expected_facts.items():
        if facts.get(field) != expected:
            errors.append(f"topology.{field} must equal {expected!r}")

    metadata = {
        "revision": revision, "environment": environment, "deployment_id": deployment_id,
        "implementer": implementer, "started_at": started_at, "ended_at": ended_at,
        "evidence_root": evidence_root, "errors": errors,
    }
    checks = manifest.get("checks")
    if not isinstance(checks, list):
        checks = []
        errors.append("checks must be a list")
    checks_by_id: dict[str, dict] = {}
    evidence_times: list[datetime] = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or not _required_text(check.get("id")):
            errors.append(f"checks[{index}].id is required")
            continue
        check_id = check["id"]
        if check_id in checks_by_id:
            errors.append(f"check {check_id} is duplicated")
            continue
        checks_by_id[check_id] = check
        observed_at, _ = _validate_metadata(check, f"check {check_id}", **metadata)
        if observed_at:
            evidence_times.append(observed_at)
    for missing in sorted(REQUIRED_CHECKS - checks_by_id.keys()):
        errors.append(f"required check {missing} is missing")

    trials = manifest.get("core_loop_trials")
    if not isinstance(trials, list) or len(trials) != 3:
        errors.append("core_loop_trials must contain exactly three consecutive trials")
        trials = trials if isinstance(trials, list) else []
    trial_times: list[datetime] = []
    trial_digests: list[str] = []
    run_ids: set[str] = set()
    for index, trial in enumerate(trials, start=1):
        if not isinstance(trial, dict):
            errors.append(f"core_loop_trials[{index - 1}] must be an object")
            continue
        label = f"core_loop trial {index}"
        if trial.get("sequence") != index:
            errors.append(f"{label} must have sequence {index}")
        run_id = _run_id(trial.get("run_id"), f"{label}.run_id", errors)
        if run_id is None or run_id in run_ids:
            errors.append(f"{label}.run_id must be unique")
        else:
            run_ids.add(run_id)
        observed_at, digest = _validate_metadata(trial, label, **metadata)
        if observed_at:
            if trial_times and observed_at <= trial_times[-1]:
                errors.append(f"{label}.observed_at must be later than the prior trial")
            trial_times.append(observed_at)
            evidence_times.append(observed_at)
        expected_previous = None if index == 1 else (trial_digests[-1] if trial_digests else None)
        if trial.get("previous_trial_sha256") != expected_previous:
            errors.append(f"{label}.previous_trial_sha256 does not chain the prior trial")
        if digest:
            if digest in trial_digests:
                errors.append(f"{label} must use a distinct evidence artifact")
            trial_digests.append(digest)
        for field in (
            "dashboard_account", "pairing", "task", "reminder_delivered", "done",
            "dashboard_synchronized", "no_duplicate", "no_cross_participant_effect",
            "no_lost_delivery",
        ):
            if trial.get(field) is not True:
                errors.append(f"{label}.{field} must be true")

    findings = manifest.get("open_findings") or {}
    if findings.get("critical") != 0:
        errors.append("open_findings.critical must be zero")
    if findings.get("gate_a_high") != 0:
        errors.append("open_findings.gate_a_high must be zero")
    findings_at, _ = _validate_metadata(
        findings, "open_findings", require_status=False, **metadata
    )
    if findings_at:
        evidence_times.append(findings_at)

    decision = manifest.get("founder_decision") or {}
    if decision.get("decision") != "pass":
        errors.append("founder_decision.decision must explicitly be pass for Gate A to pass")
    founder = _actor_id(decision.get("founder"), "founder_decision.founder", errors)
    reviewer = _actor_id(decision.get("reviewer"), "founder_decision.reviewer", errors)
    for field in ("founder", "reviewer", "revision", "environment", "deployment_id"):
        if not _required_text(decision.get(field)):
            errors.append(f"founder_decision.{field} is required")
    if founder == reviewer:
        errors.append("founder_decision must have a distinct decision witness")
    if reviewer == implementer:
        errors.append("founder_decision cannot be witnessed by the release implementer")
    if decision.get("revision") != revision or decision.get("environment") != environment:
        errors.append("founder_decision does not match the tested release/environment")
    if decision.get("deployment_id") != deployment_id:
        errors.append("founder_decision.deployment_id does not match the release")
    recorded_at = _parse_timestamp(
        decision.get("recorded_at"), "founder_decision.recorded_at", errors
    )
    if recorded_at and started_at and recorded_at < started_at:
        errors.append("founder_decision.recorded_at predates evidence collection")
    if recorded_at and ended_at and recorded_at > ended_at:
        errors.append("founder_decision.recorded_at is after evidence collection ended")
    if recorded_at and evidence_times and recorded_at < max(evidence_times):
        errors.append("founder_decision.recorded_at must follow all reviewed evidence")
    _validate_evidence(decision.get("evidence"), "founder_decision.evidence", evidence_root, errors)
    security_review = checks_by_id.get("independent_security_review") or {}
    security_people = {
        str(security_review.get("producer", "")).strip().casefold(),
        str(security_review.get("reviewer", "")).strip().casefold(),
    }
    if implementer in security_people:
        errors.append("release implementer cannot produce or approve the security review")
    if founder in security_people:
        errors.append("founder cannot approve their own required independent security review")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, nargs="?")
    parser.add_argument("--template", action="store_true")
    args = parser.parse_args()
    if args.template:
        print(json.dumps(template_manifest(), indent=2, sort_keys=True))
        return 0
    if args.manifest is None:
        parser.error("manifest is required unless --template is used")
    manifest = json.loads(args.manifest.read_text())
    errors = validate_manifest(manifest, evidence_root=args.manifest.parent)
    if errors:
        print("Internal Preflight evidence: NOT PASSING")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Internal Preflight evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
