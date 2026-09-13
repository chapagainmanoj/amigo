"""Internal Preflight release-evidence contract tests."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from scripts.validate_preflight_evidence import (
    REQUIRED_CHECKS,
    template_manifest,
    validate_manifest,
)
from src.evaluation.gate_a import THRESHOLDS, summarize_scores
from tests.gate_a_fixtures import passing_gate_a_evidence

REVISION = "a" * 40
DEPLOYMENT_ID = "render-deploy-123"
NOW = datetime(2026, 9, 3, tzinfo=UTC)


def _artifact(root: Path, name: str, content: str) -> dict:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return {"path": name, "sha256": hashlib.sha256(content.encode()).hexdigest()}


def _evidence_item(root: Path, item_id: str, sequence: int) -> dict:
    return {
        "id": item_id,
        "status": "pass",
        "producer": "implementer",
        "reviewer": "independent-reviewer",
        "observed_at": f"2026-09-02T01:{sequence:02d}:00Z",
        "revision": REVISION,
        "environment": "staging",
        "deployment_id": DEPLOYMENT_ID,
        "evidence": _artifact(root, f"checks/{item_id}.json", item_id),
    }


def passing_manifest(root: Path) -> dict:
    checks = [
        _evidence_item(root, check_id, sequence)
        for sequence, check_id in enumerate(sorted(REQUIRED_CHECKS), start=1)
    ]
    security = next(check for check in checks if check["id"] == "independent_security_review")
    security["producer"] = "security-reviewer"
    security["reviewer"] = "security-witness"

    # The Gate A artifact is cross-checked against the release revision, so it must be the real
    # declared-run JSON rather than an opaque placeholder.
    evaluation = next(check for check in checks if check["id"] == "model_evaluation")
    evaluation["evidence"] = _artifact(
        root,
        "checks/model_evaluation.json",
        json.dumps(passing_gate_a_evidence(REVISION)),
    )

    trials = []
    previous_digest = None
    for sequence in (1, 2, 3):
        evidence = _artifact(root, f"trials/{sequence}.json", f"core-loop-{sequence}")
        trials.append(
            {
                "sequence": sequence,
                "run_id": f"staging-run-{sequence}",
                "previous_trial_sha256": previous_digest,
                "status": "pass",
                "producer": "operator",
                "reviewer": "independent-reviewer",
                "observed_at": f"2026-09-02T01:3{sequence}:00Z",
                "revision": REVISION,
                "environment": "staging",
                "deployment_id": DEPLOYMENT_ID,
                "evidence": evidence,
                "dashboard_account": True,
                "pairing": True,
                "task": True,
                "reminder_delivered": True,
                "done": True,
                "dashboard_synchronized": True,
                "no_duplicate": True,
                "no_cross_participant_effect": True,
                "no_lost_delivery": True,
            }
        )
        previous_digest = evidence["sha256"]

    return {
        "schema_version": "amigo-internal-preflight-v1",
        "release": {
            "revision": REVISION,
            "environment": "staging",
            "deployment_id": DEPLOYMENT_ID,
            "started_at": "2026-09-02T01:00:00Z",
            "ended_at": "2026-09-02T02:00:00Z",
            "operator": "operator",
            "implementer": "implementer",
        },
        "topology": {
            "render_backend_instances": 1,
            "scheduler_owners": 1,
            "webhook_destinations": 1,
            "fly_active": False,
            "always_on": True,
            "telegram_resource_separate": True,
            "supabase_resource_separate": True,
            "dashboard_resource_separate": True,
            "model_resource_separate": True,
        },
        "checks": checks,
        "core_loop_trials": trials,
        "open_findings": {
            "critical": 0,
            "gate_a_high": 0,
            "producer": "release-owner",
            "reviewer": "independent-reviewer",
            "observed_at": "2026-09-02T01:45:00Z",
            "revision": REVISION,
            "environment": "staging",
            "deployment_id": DEPLOYMENT_ID,
            "evidence": _artifact(root, "findings.json", "zero-open-blockers"),
        },
        "founder_decision": {
            "decision": "pass",
            "founder": "founder",
            "reviewer": "decision-witness",
            "recorded_at": "2026-09-02T01:59:00Z",
            "revision": REVISION,
            "environment": "staging",
            "deployment_id": DEPLOYMENT_ID,
            "evidence": _artifact(root, "founder-decision.md", "Gate A: pass"),
        },
    }


def _validate(manifest: dict, root: Path) -> list[str]:
    return validate_manifest(manifest, evidence_root=root, now=NOW)


def test_complete_independently_reviewed_manifest_passes(tmp_path):
    assert _validate(passing_manifest(tmp_path), tmp_path) == []


def test_generated_capture_template_is_complete_shape_but_cannot_pass(tmp_path):
    template = template_manifest()
    assert {check["id"] for check in template["checks"]} == REQUIRED_CHECKS
    assert len(template["core_loop_trials"]) == 3
    assert _validate(template, tmp_path)


def test_missing_unknown_or_unverifiable_evidence_fails_closed(tmp_path):
    manifest = passing_manifest(tmp_path)
    manifest["checks"] = [
        check for check in manifest["checks"] if check["id"] != "clean_migrations"
    ]
    manifest["checks"][0]["status"] = "unknown"
    manifest["checks"][1]["evidence"]["path"] = "missing.json"
    manifest["checks"][2]["evidence"]["sha256"] = "0" * 64

    errors = _validate(manifest, tmp_path)
    assert "required check clean_migrations is missing" in errors
    assert any("is not passing" in error for error in errors)
    assert any("path does not exist" in error for error in errors)
    assert any("sha256 does not match" in error for error in errors)


def test_invalid_reversed_out_of_window_and_future_timestamps_fail(tmp_path):
    manifest = passing_manifest(tmp_path)
    manifest["release"]["ended_at"] = "2026-09-04T00:00:00Z"
    manifest["checks"][0]["observed_at"] = "2020-01-01T00:00:00Z"
    manifest["checks"][1]["observed_at"] = "2026-99-99T99:99:99Z"

    errors = _validate(manifest, tmp_path)
    assert any("must be a real UTC timestamp" in error for error in errors)
    assert "release.ended_at cannot be in the future" in errors
    assert any("predates evidence collection" in error for error in errors)

    reversed_manifest = passing_manifest(tmp_path)
    reversed_manifest["release"]["started_at"] = "2026-09-02T02:00:00Z"
    reversed_manifest["release"]["ended_at"] = "2026-09-02T01:00:00Z"
    assert (
        "release.ended_at must be after release.started_at"
        in _validate(reversed_manifest, tmp_path)
    )


def test_three_trials_must_be_distinct_ordered_and_hash_chained(tmp_path):
    manifest = passing_manifest(tmp_path)
    first = manifest["core_loop_trials"][0]
    second = manifest["core_loop_trials"][1]
    second["run_id"] = first["run_id"]
    second["observed_at"] = first["observed_at"]
    second["evidence"] = deepcopy(first["evidence"])

    errors = _validate(manifest, tmp_path)
    assert "core_loop trial 2.run_id must be unique" in errors
    assert "core_loop trial 2.observed_at must be later than the prior trial" in errors
    assert "core_loop trial 2 must use a distinct evidence artifact" in errors


def test_revision_deployment_and_independent_review_binding_fail_closed(tmp_path):
    manifest = passing_manifest(tmp_path)
    manifest["checks"][0]["revision"] = "b" * 40
    manifest["checks"][1]["deployment_id"] = "different-deploy"
    manifest["checks"][2]["reviewer"] = "implementer"
    security = next(
        check for check in manifest["checks"] if check["id"] == "independent_security_review"
    )
    security["producer"] = "implementer"
    manifest["founder_decision"]["founder"] = security["reviewer"]
    manifest["founder_decision"]["reviewer"] = "implementer"

    errors = _validate(manifest, tmp_path)
    assert any("revision does not match" in error for error in errors)
    assert any("deployment_id does not match" in error for error in errors)
    assert any("cannot be reviewed by the release implementer" in error for error in errors)
    assert "release implementer cannot produce or approve the security review" in errors
    assert "founder cannot approve their own required independent security review" in errors
    assert "founder_decision cannot be witnessed by the release implementer" in errors


def test_explicit_founder_failure_cannot_be_reported_as_gate_passage(tmp_path):
    manifest = passing_manifest(tmp_path)
    manifest["founder_decision"]["decision"] = "fail"
    manifest["founder_decision"]["recorded_at"] = "2026-09-02T01:01:00Z"
    errors = _validate(manifest, tmp_path)
    assert "founder_decision.decision must explicitly be pass for Gate A to pass" in errors
    assert "founder_decision.recorded_at must follow all reviewed evidence" in errors


def test_actor_aliases_and_run_id_aliases_cannot_fake_independence(tmp_path):
    manifest = passing_manifest(tmp_path)
    manifest["release"]["implementer"] = "alice"
    manifest["checks"][0]["producer"] = "ALICE"
    manifest["checks"][0]["reviewer"] = " Alice "
    security = next(
        check for check in manifest["checks"] if check["id"] == "independent_security_review"
    )
    security["reviewer"] = "ALICE"
    manifest["founder_decision"]["founder"] = "Alice"
    manifest["founder_decision"]["reviewer"] = " alice "
    manifest["core_loop_trials"][1]["run_id"] = "STAGING-RUN-1"

    errors = _validate(manifest, tmp_path)
    assert any("canonical lowercase stable actor ID" in error for error in errors)
    assert any("producer and reviewer must be different" in error for error in errors)
    assert "release implementer cannot produce or approve the security review" in errors
    assert any("canonical lowercase stable run ID" in error for error in errors)
    assert "core_loop trial 2.run_id must be unique" in errors


def test_a_gate_a_run_from_another_revision_cannot_be_attached(tmp_path):
    """`model_evaluation.revision` is typed by a human; the artifact must prove itself."""
    manifest = passing_manifest(tmp_path)
    stale = passing_gate_a_evidence("b" * 40)
    evaluation = next(check for check in manifest["checks"] if check["id"] == "model_evaluation")
    evaluation["evidence"] = _artifact(
        tmp_path, "checks/model_evaluation.json", json.dumps(stale)
    )

    errors = validate_manifest(manifest, evidence_root=tmp_path, now=NOW)

    assert any(
        error.startswith("check model_evaluation: the declared run was executed against")
        for error in errors
    ), errors


def test_a_gate_a_run_that_predates_a_model_input_change_is_rejected(tmp_path):
    manifest = passing_manifest(tmp_path)
    stale = passing_gate_a_evidence(REVISION)
    stale["release_inputs"]["all_invalidating_inputs_sha256"] = "0" * 64
    evaluation = next(check for check in manifest["checks"] if check["id"] == "model_evaluation")
    evaluation["evidence"] = _artifact(
        tmp_path, "checks/model_evaluation.json", json.dumps(stale)
    )

    errors = validate_manifest(manifest, evidence_root=tmp_path, now=NOW)

    assert any("Gate A must run again" in error for error in errors), errors


def test_an_opaque_model_evaluation_artifact_is_rejected(tmp_path):
    manifest = passing_manifest(tmp_path)
    evaluation = next(check for check in manifest["checks"] if check["id"] == "model_evaluation")
    evaluation["evidence"] = _artifact(
        tmp_path, "checks/model_evaluation.json", "screenshot of a green run"
    )

    errors = validate_manifest(manifest, evidence_root=tmp_path, now=NOW)

    assert "check model_evaluation.evidence must be the declared Gate A run JSON" in errors


def test_a_failed_gate_a_run_cannot_pass_the_manifest(tmp_path):
    manifest = passing_manifest(tmp_path)
    failed = passing_gate_a_evidence(REVISION)
    failed["status"] = "failed"
    failed["passed"] = False
    for execution in failed["executions"]:
        if "hard_invariant" in execution["metric_results"]:
            execution["metric_results"]["hard_invariant"] = False
            execution["passed"] = False
    failed["scores"] = summarize_scores(failed["executions"], THRESHOLDS)
    evaluation = next(check for check in manifest["checks"] if check["id"] == "model_evaluation")
    evaluation["evidence"] = _artifact(
        tmp_path, "checks/model_evaluation.json", json.dumps(failed)
    )

    errors = validate_manifest(manifest, evidence_root=tmp_path, now=NOW)

    assert any("did not pass" in error for error in errors), errors
    assert any("scores.hard_invariant did not meet" in error for error in errors), errors
