"""A declared Gate A run must not be presentable as evidence for a tree it never ran against."""

import ast
import hashlib
import json
import sys
from pathlib import Path

import pytest

from scripts.check_gate_a_evidence import ROOT
from scripts.check_gate_a_evidence import check_evidence as _check_evidence
from src.evaluation.gate_a import (
    GATE_A_ENTRY_MODULES,
    INVALIDATING_INPUT_PATHS,
    THRESHOLDS,
    build_baseline_comparison,
    execution_metric_results,
    gate_a_state_hash,
    load_suite,
    score_turn,
    summarize_scores,
)
from tests.gate_a_fixtures import passing_gate_a_bundle, passing_gate_a_evidence

REVISION = "0" * 39 + "a"
CASES_BY_ID = {case.id: case for case in load_suite(ROOT / "evals/gate_a/v1/cases.json").cases}


def _passing_evidence() -> dict:
    return passing_gate_a_evidence(REVISION)


def _artifact_sha(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def _approved_comparison(evidence, baseline, baseline_sha256):
    candidate_sha256 = _artifact_sha(evidence)
    approved = build_baseline_comparison(
        evidence,
        baseline,
        candidate_artifact_sha256=candidate_sha256,
        baseline_artifact_sha256=baseline_sha256,
    )
    approved["human_review"] = {
        "status": "approved",
        "reviewer": "independent-reviewer",
        "reviewed_at": "2026-09-02T01:07:00Z",
        "baseline_confirmed_last_passing": True,
        "tone_reviewed": True,
        "reviewed_new_failure_pattern_ids": [
            pattern["id"] for pattern in approved["failure_patterns"]["new"]
        ],
        "notes": "Reviewed tone, score deltas, and every new failure pattern.",
    }
    return approved


def _forge_passing_scores_over_bad_turn_evidence(evidence: dict) -> None:
    """Leave stored booleans green while the retained transcript proves two violations."""
    execution = next(
        item
        for item in evidence["executions"]
        if item["case_id"] == "ga-life-15" and item["repetition"] == 1
    )
    turn = execution["turns"][0]
    assert turn["score"]["passed"] is True
    _append_call_result(turn, "apply_later")
    turn["response"] = "नमस्ते"


def _append_call_result(turn: dict, tool: str) -> None:
    call_id = f"adversarial-call-{len(turn['trace'])}"
    turn["trace"].extend(
        [
            {"kind": "tool_call", "tool": tool, "call_id": call_id, "args": {}},
            {
                "kind": "tool_result",
                "tool": tool,
                "call_id": call_id,
                "content": "{}",
            },
        ]
    )
    turn["usage"]["tool_calls"] += 1


def _rehash_state(state: dict) -> None:
    tasks_by_id = {task["task_id"]: task for task in state["tasks"]}
    state["aliases"] = {
        alias: tasks_by_id[task["task_id"]] for alias, task in state["aliases"].items()
    }
    state["state_hash"] = gate_a_state_hash(
        state["tasks"], state["pending_reminders"], state["aliases"]
    )


def _fail_metric(item: dict, metric: str) -> None:
    """Create genuinely failing retained evidence, then record its independently derived result."""
    case = CASES_BY_ID[item["case_id"]]
    for turn_index, (authored, retained) in enumerate(
        zip(case.turns, item["turns"], strict=True), start=1
    ):
        if metric in {
            "hard_invariant",
            "safety_boundary",
            "tool_and_state",
            "no_unnecessary_mutation",
        }:
            _append_call_result(retained, authored.prohibited_tools[0])
        elif metric == "mutation_risk_clarification":
            if authored.expected_state.unchanged:
                if retained["state"]["tasks"]:
                    retained["state"]["tasks"][0]["version"] += turn_index
                else:
                    retained["state"]["tasks"].append(
                        {
                            "task_id": f"unexpected-{turn_index}",
                            "title": "Unexpected mutation",
                            "status": "pending",
                            "due_date": None,
                            "version": 1,
                        }
                    )
                _rehash_state(retained["state"])
        elif metric == "task_extraction":
            expected_count = authored.expected_state.task_count
            if expected_count:
                for task in retained["state"]["tasks"]:
                    task["title"] = "Unexpected fixture task"
            else:
                retained["state"]["tasks"].append(
                    {
                        "task_id": f"unexpected-{turn_index}",
                        "title": "Unexpected fixture task",
                        "status": "pending",
                        "due_date": None,
                        "version": 1,
                    }
                )
            _rehash_state(retained["state"])
        elif metric == "clarification":
            if authored.clarification == "required":
                retained["response"] = retained["response"].replace("?", ".")
        elif metric in {"english", "factual_consistency"}:
            retained["response"] = "नमस्ते"
        elif metric == "tone":
            retained["response"] += " You failed."

    for index, (authored, retained) in enumerate(
        zip(case.turns, item["turns"], strict=True)
    ):
        if index:
            retained["before_state_hash"] = item["turns"][index - 1]["state"][
                "state_hash"
            ]
        retained["score"] = score_turn(
            authored,
            trace=retained["trace"],
            response=retained["response"],
            state=retained["state"],
            before_state_hash=retained["before_state_hash"],
        )
    item["metric_results"] = execution_metric_results(
        case, [turn["score"] for turn in item["turns"]]
    )
    item["passed"] = all(item["metric_results"].values())


def check_evidence(evidence, *, revision, **kwargs):
    """Exercise candidate validation with a valid baseline/comparison unless overridden."""
    _, baseline, baseline_sha256, approved = passing_gate_a_bundle(revision)
    if isinstance(evidence, dict):
        approved = _approved_comparison(evidence, baseline, baseline_sha256)
    return _check_evidence(
        evidence,
        revision=revision,
        baseline_evidence=kwargs.pop("baseline_evidence", baseline),
        candidate_sha256=kwargs.pop(
            "candidate_sha256",
            _artifact_sha(evidence) if isinstance(evidence, dict) else None,
        ),
        baseline_sha256=kwargs.pop("baseline_sha256", baseline_sha256),
        comparison=kwargs.pop("comparison", approved),
        **kwargs,
    )


def test_a_complete_passing_run_against_this_tree_is_accepted():
    assert check_evidence(_passing_evidence(), revision=REVISION) == []


def test_release_evidence_fails_closed_without_an_archived_baseline():
    evidence = _passing_evidence()

    errors = _check_evidence(evidence, revision=REVISION)

    assert "the archived last-passing Gate A baseline artifact is required" in errors


def test_malformed_candidate_identifiers_fail_closed_instead_of_crashing():
    evidence = _passing_evidence()
    evidence["selected_cases"][0] = 1
    evidence["executions"][0]["case_id"] = []
    evidence["scores"]["tone"] = []

    errors = check_evidence(evidence, revision=REVISION)

    assert any("development subset" in error for error in errors)
    assert "every execution must record a string case_id" in errors
    assert "evidence.scores does not match the recorded executions" in errors


def test_malformed_baseline_metadata_fails_closed_instead_of_crashing():
    candidate, baseline, baseline_sha256, comparison = passing_gate_a_bundle(REVISION)
    baseline["release_inputs"] = []

    errors = _check_evidence(
        candidate,
        revision=REVISION,
        baseline_evidence=baseline,
        candidate_sha256=_artifact_sha(candidate),
        baseline_sha256=baseline_sha256,
        comparison=comparison,
    )

    assert "historical baseline git revision is invalid" in errors
    assert any("baseline_comparison.baseline" in error for error in errors)


def test_each_execution_is_bound_to_its_authored_category_metrics_and_turns():
    evidence = _passing_evidence()
    execution = evidence["executions"][0]
    execution["category"] = "hard_invariant"
    execution["metric_results"] = {"tone": True}
    execution["turns"] = []

    errors = check_evidence(evidence, revision=REVISION)

    assert any("category does not match the authored case" in error for error in errors)
    assert any("metric_results does not match the authored case" in error for error in errors)
    assert any("must record every authored turn" in error for error in errors)


def test_179_empty_metric_sets_and_one_all_metric_set_cannot_pass_vacuously():
    evidence = _passing_evidence()
    for execution in evidence["executions"][:-1]:
        execution["metric_results"] = {}
    evidence["executions"][-1]["metric_results"] = dict.fromkeys(THRESHOLDS, True)
    evidence["scores"] = summarize_scores(evidence["executions"], THRESHOLDS)

    errors = check_evidence(evidence, revision=REVISION)

    assert any("metric_results does not match the authored case" in error for error in errors)
    assert "evidence.scores does not match the recorded executions" in errors


def test_stored_passing_booleans_cannot_hide_prohibited_tool_and_language_failures():
    evidence = _passing_evidence()
    _forge_passing_scores_over_bad_turn_evidence(evidence)

    errors = check_evidence(evidence, revision=REVISION)

    assert any("score does not match recomputed turn evidence" in error for error in errors)
    assert any("metric_results does not match its turn evidence" in error for error in errors)
    assert "evidence.scores does not match the recorded executions" in errors


def test_cli_rescores_retained_turn_evidence_instead_of_trusting_booleans(
    tmp_path, capsys
):
    from scripts.check_gate_a_evidence import main

    candidate, baseline, baseline_sha256, _ = passing_gate_a_bundle(REVISION)
    _forge_passing_scores_over_bad_turn_evidence(candidate)
    comparison = _approved_comparison(candidate, baseline, baseline_sha256)
    candidate_path = tmp_path / "candidate.json"
    baseline_path = tmp_path / "baseline.json"
    comparison_path = tmp_path / "comparison.json"
    candidate_path.write_text(json.dumps(candidate))
    baseline_path.write_text(json.dumps(baseline))
    comparison_path.write_text(json.dumps(comparison))
    original = sys.argv
    sys.argv = [
        "check",
        "--evidence",
        str(candidate_path),
        "--baseline",
        str(baseline_path),
        "--comparison",
        str(comparison_path),
        "--revision",
        REVISION,
    ]
    try:
        assert main() == 1
    finally:
        sys.argv = original

    output = capsys.readouterr().out
    assert "score does not match recomputed turn evidence" in output
    assert "baseline_comparison.candidate" not in output


@pytest.mark.parametrize("which", ["candidate", "baseline"])
def test_non_list_execution_collections_fail_closed(which):
    candidate, baseline, baseline_sha256, _ = passing_gate_a_bundle(REVISION)
    target = candidate if which == "candidate" else baseline
    target["executions"] = 5
    comparison = _approved_comparison(candidate, baseline, baseline_sha256)

    errors = _check_evidence(
        candidate,
        revision=REVISION,
        baseline_evidence=baseline,
        candidate_sha256=_artifact_sha(candidate),
        baseline_sha256=baseline_sha256,
        comparison=comparison,
    )

    prefix = "" if which == "candidate" else "historical baseline: "
    assert f"{prefix}evidence.executions is required" in errors


@pytest.mark.parametrize(
    "malformed_state",
    [
        {"tasks": 5, "pending_reminders": [], "aliases": {}, "state_hash": "x"},
        {"tasks": [5], "pending_reminders": [], "aliases": {}, "state_hash": "x"},
        {"tasks": [], "pending_reminders": [], "aliases": {"x": []}, "state_hash": "x"},
        {
            "tasks": [
                {
                    "task_id": "task-1",
                    "title": "Task",
                    "status": [],
                    "due_date": None,
                    "version": 1,
                }
            ],
            "pending_reminders": [],
            "aliases": {},
            "state_hash": "0" * 64,
        },
    ],
)
def test_malformed_nested_turn_state_returns_errors(malformed_state):
    evidence = _passing_evidence()
    evidence["executions"][0]["turns"][0]["state"] = malformed_state

    errors = check_evidence(evidence, revision=REVISION)

    assert any(".state " in error for error in errors)


@pytest.mark.parametrize("kind", [[], {}, 1, None])
def test_unhashable_or_non_string_trace_kind_returns_an_error(kind):
    evidence = _passing_evidence()
    evidence["executions"][0]["turns"][0]["trace"][0]["kind"] = kind

    errors = check_evidence(evidence, revision=REVISION)

    assert any("trace[0].kind is invalid" in error for error in errors)


@pytest.mark.parametrize(
    ("trace", "expected_error"),
    [
        (
            [
                {
                    "kind": "tool_call",
                    "tool": "invented_tool",
                    "call_id": "unknown-1",
                    "args": {},
                },
                {
                    "kind": "tool_result",
                    "tool": "invented_tool",
                    "call_id": "unknown-1",
                    "content": "{}",
                },
            ],
            "must name a known Gate A Tool",
        ),
        (
            [
                {
                    "kind": "tool_result",
                    "tool": "create_task",
                    "call_id": "orphan-1",
                    "content": "{}",
                }
            ],
            "orphan Tool result",
        ),
        (
            [
                {
                    "kind": "tool_call",
                    "tool": "create_task",
                    "call_id": "mismatch-1",
                    "args": {},
                },
                {
                    "kind": "tool_result",
                    "tool": "apply_later",
                    "call_id": "mismatch-1",
                    "content": "{}",
                },
            ],
            "tool does not match its Tool call",
        ),
        (
            [
                {
                    "kind": "tool_call",
                    "tool": "create_task",
                    "call_id": "missing-1",
                    "args": {},
                }
            ],
            "Tool calls without matching result IDs",
        ),
        (
            [
                {
                    "kind": "tool_call",
                    "tool": "create_task",
                    "call_id": "empty-1",
                    "args": {},
                },
                {
                    "kind": "tool_result",
                    "tool": "create_task",
                    "call_id": "empty-1",
                    "content": "   ",
                },
            ],
            "is not a valid Tool result",
        ),
    ],
)
def test_trace_requires_known_tools_and_complete_call_result_pairs(trace, expected_error):
    evidence = _passing_evidence()
    turn = evidence["executions"][0]["turns"][0]
    turn["trace"] = trace
    turn["usage"]["tool_calls"] = sum(
        item.get("kind") == "tool_call" for item in trace
    )

    errors = check_evidence(evidence, revision=REVISION)

    assert any(expected_error in error for error in errors)


def test_state_aliases_hash_and_multi_turn_chain_are_independently_verified():
    evidence = _passing_evidence()
    aliased = next(
        item for item in evidence["executions"] if item["case_id"] == "ga-life-01"
    )
    alias_task = dict(aliased["turns"][0]["state"]["aliases"]["report"])
    alias_task["title"] = "Contradiction"
    aliased["turns"][0]["state"]["aliases"]["report"] = alias_task
    fabricated = evidence["executions"][0]["turns"][0]["state"]
    fabricated["tasks"][0]["title"] = "Hidden mutation"
    multi = next(
        item for item in evidence["executions"] if item["case_id"] == "ga-task-04"
    )
    multi["turns"][1]["before_state_hash"] = "0" * 64

    errors = check_evidence(evidence, revision=REVISION)

    assert any("contradicts the retained task" in error for error in errors)
    assert any("state_hash does not match the retained domain state" in error for error in errors)
    assert any("before_state_hash does not chain the prior turn" in error for error in errors)


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("environment", None, "evidence.environment"),
        ("minimum_provider_request_interval_seconds", True, "request_interval"),
        ("pricing", {}, "evidence.pricing"),
        ("policy", None, "evidence.policy"),
        ("totals", {}, "evidence.totals"),
    ],
)
def test_required_run_metadata_cannot_be_deleted_or_mistyped(field, value, expected_error):
    evidence = _passing_evidence()
    evidence[field] = value

    errors = check_evidence(evidence, revision=REVISION)

    assert any(expected_error in error for error in errors)


@pytest.mark.parametrize(
    "field",
    [
        "working_tree_diff_sha256",
        "provider_model",
        "model_settings",
        "tool_schema",
        "case_set_version",
        "fixed_utc",
        "timezone",
    ],
)
def test_required_release_input_metadata_cannot_be_deleted(field):
    evidence = _passing_evidence()
    del evidence["release_inputs"][field]

    errors = check_evidence(evidence, revision=REVISION)

    assert any(field in error for error in errors)


@pytest.mark.parametrize("field", ["latency_ms", "usage", "estimated_cost_usd"])
def test_execution_aggregates_are_derived_from_turn_evidence(field):
    evidence = _passing_evidence()
    evidence["executions"][0][field] = None

    errors = check_evidence(evidence, revision=REVISION)

    assert any(f".{field}" in error for error in errors)


def test_comparison_binds_finalized_candidate_bytes_including_trace_only_changes():
    candidate, baseline, baseline_sha256, comparison = passing_gate_a_bundle(REVISION)
    candidate["executions"][0]["turns"][0]["trace"][0]["args"] = {
        "title": "tampered"
    }

    errors = _check_evidence(
        candidate,
        revision=REVISION,
        baseline_evidence=baseline,
        candidate_sha256=_artifact_sha(candidate),
        baseline_sha256=baseline_sha256,
        comparison=comparison,
    )

    assert errors == [
        "baseline_comparison.candidate does not match the two run artifacts"
    ]


def test_cli_recomputes_candidate_digest_after_a_trace_only_change(tmp_path, capsys):
    from scripts.check_gate_a_evidence import main

    candidate, baseline, _, comparison = passing_gate_a_bundle(REVISION)
    candidate_path = tmp_path / "candidate.json"
    baseline_path = tmp_path / "baseline.json"
    comparison_path = tmp_path / "comparison.json"
    candidate_path.write_text(json.dumps(candidate))
    baseline_path.write_text(json.dumps(baseline))
    comparison_path.write_text(json.dumps(comparison))
    original = sys.argv
    sys.argv = [
        "check",
        "--evidence",
        str(candidate_path),
        "--baseline",
        str(baseline_path),
        "--comparison",
        str(comparison_path),
        "--revision",
        REVISION,
    ]
    try:
        assert main() == 0
        candidate["executions"][0]["turns"][0]["trace"][0]["args"] = {
            "title": "tampered"
        }
        candidate_path.write_text(json.dumps(candidate))
        assert main() == 1
    finally:
        sys.argv = original

    output = capsys.readouterr().out
    assert "baseline_comparison.candidate" in output
    assert "invalid trace" not in output


@pytest.mark.parametrize("repetition", [[], True, False, 0, 4, "1"])
def test_malformed_repetition_values_return_errors_instead_of_crashing(repetition):
    evidence = _passing_evidence()
    evidence["executions"][0]["repetition"] = repetition

    errors = check_evidence(evidence, revision=REVISION)

    assert any("must be a non-boolean integer from 1 through 3" in error for error in errors)


def test_a_nonpassing_run_cannot_be_selected_as_the_baseline():
    candidate, baseline, baseline_sha256, _ = passing_gate_a_bundle(REVISION)
    baseline["status"] = "failed"
    baseline["passed"] = False
    comparison = _approved_comparison(candidate, baseline, baseline_sha256)

    errors = _check_evidence(
        candidate,
        revision=REVISION,
        baseline_evidence=baseline,
        candidate_sha256=_artifact_sha(candidate),
        baseline_sha256=baseline_sha256,
        comparison=comparison,
    )

    assert any("historical baseline: the declared run did not pass" in error for error in errors)


def test_candidate_cannot_compare_itself_or_a_later_run_as_its_baseline():
    candidate, baseline, baseline_sha256, _ = passing_gate_a_bundle(REVISION)
    baseline["run_id"] = candidate["run_id"]
    baseline["completed_at"] = candidate["declared_at"]
    comparison = _approved_comparison(candidate, baseline, baseline_sha256)

    errors = _check_evidence(
        candidate,
        revision=REVISION,
        baseline_evidence=baseline,
        candidate_sha256=_artifact_sha(candidate),
        baseline_sha256=baseline_sha256,
        comparison=comparison,
    )

    assert "candidate and historical baseline must be distinct declared runs" in errors
    assert "historical baseline must predate candidate declaration" in errors


def test_a_pending_or_unconfirmed_baseline_comparison_is_not_release_evidence():
    candidate, baseline, baseline_sha256, comparison = passing_gate_a_bundle(REVISION)
    comparison["human_review"]["status"] = "pending"
    comparison["human_review"]["baseline_confirmed_last_passing"] = False
    comparison["human_review"]["tone_reviewed"] = False

    errors = _check_evidence(
        candidate,
        revision=REVISION,
        baseline_evidence=baseline,
        candidate_sha256=_artifact_sha(candidate),
        baseline_sha256=baseline_sha256,
        comparison=comparison,
    )

    assert "baseline comparison human review is not approved" in errors
    assert "human review must confirm the selected baseline is the last passing run" in errors
    assert "human review must explicitly review the subjective tone results" in errors


def test_score_deltas_are_recomputed_from_candidate_and_baseline():
    candidate, baseline, baseline_sha256, comparison = passing_gate_a_bundle(REVISION)
    comparison["score_comparison"]["tone"]["delta"] = -0.5

    errors = _check_evidence(
        candidate,
        revision=REVISION,
        baseline_evidence=baseline,
        candidate_sha256=_artifact_sha(candidate),
        baseline_sha256=baseline_sha256,
        comparison=comparison,
    )

    assert (
        "baseline_comparison.score_comparison does not match the two run artifacts" in errors
    )


def test_every_new_failure_pattern_must_be_reported_and_human_reviewed():
    candidate, baseline, baseline_sha256, _ = passing_gate_a_bundle(REVISION)
    execution = next(
        item for item in candidate["executions"] if "tone" in item["metric_results"]
    )
    _fail_metric(execution, "tone")
    candidate["scores"] = summarize_scores(candidate["executions"], THRESHOLDS)
    candidate["passed"] = all(score["passed"] for score in candidate["scores"].values())
    candidate["status"] = "passed" if candidate["passed"] else "failed"
    assert candidate["passed"], "one tone miss should remain above its approved threshold"
    comparison = _approved_comparison(candidate, baseline, baseline_sha256)
    assert comparison["failure_patterns"]["new"]
    assert (
        _check_evidence(
            candidate,
            revision=REVISION,
            baseline_evidence=baseline,
            candidate_sha256=_artifact_sha(candidate),
            baseline_sha256=baseline_sha256,
            comparison=comparison,
        )
        == []
    )
    comparison["human_review"]["reviewed_new_failure_pattern_ids"] = []

    errors = _check_evidence(
        candidate,
        revision=REVISION,
        baseline_evidence=baseline,
        candidate_sha256=_artifact_sha(candidate),
        baseline_sha256=baseline_sha256,
        comparison=comparison,
    )

    assert "human review must enumerate every new failure pattern exactly" in errors


@pytest.mark.parametrize(
    "fingerprint",
    [
        "prompt_source_sha256",
        "validator_source_sha256",
        "turn_context_source_sha256",
        "time_behavior_source_sha256",
        "all_invalidating_inputs_sha256",
        "case_set_sha256",
    ],
)
def test_any_changed_invalidating_input_forces_a_new_run(fingerprint):
    evidence = _passing_evidence()
    evidence["release_inputs"][fingerprint] = "0" * 64

    errors = check_evidence(evidence, revision=REVISION)

    assert any(fingerprint in error and "must run again" in error for error in errors)


def test_evidence_from_another_revision_is_refused():
    evidence = _passing_evidence()
    evidence["release_inputs"]["git_revision"] = "b" * 40

    assert any(
        error.startswith("the declared run was executed against") and REVISION in error
        for error in check_evidence(evidence, revision=REVISION)
    )


def test_a_dirty_working_tree_is_refused():
    evidence = _passing_evidence()
    evidence["release_inputs"]["working_tree_dirty"] = True

    assert any("dirty working tree" in error for error in check_evidence(
        evidence, revision=REVISION
    ))


def test_a_development_subset_is_not_release_evidence():
    evidence = _passing_evidence()
    evidence["selected_cases"] = ["ga-task-01"]
    evidence["executions"] = evidence["executions"][:3]

    errors = check_evidence(evidence, revision=REVISION)

    assert any("development subset" in error for error in errors)
    assert any("expected 180 executions" in error for error in errors)


def test_a_missing_repetition_is_refused():
    evidence = _passing_evidence()
    evidence["executions"] = [
        item for item in evidence["executions"]
        if not (item["case_id"] == "ga-hard-01" and item["repetition"] == 3)
    ]

    assert any(
        "ga-hard-01 did not run repetitions 1, 2 and 3 (found ['1', '2'])" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


def test_an_aborted_quota_run_is_refused():
    evidence = _passing_evidence()
    evidence["status"] = "aborted_provider_incident"
    evidence["passed"] = False
    evidence["provider_incidents"] = [{"type": "quota_exhausted", "status_code": 429}]

    errors = check_evidence(evidence, revision=REVISION)

    assert any("did not pass" in error for error in errors)
    assert any("provider incident" in error for error in errors)


def test_an_errored_execution_is_refused():
    evidence = _passing_evidence()
    evidence["executions"][7]["status"] = "error"

    assert any(
        "did not complete" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


@pytest.mark.parametrize("metric", sorted(THRESHOLDS))
def test_every_metric_must_meet_its_approved_threshold(metric):
    """Fail the metric in the executions themselves, not in the recorded summary."""
    evidence = _passing_evidence()
    for item in evidence["executions"]:
        if metric in item["metric_results"]:
            _fail_metric(item, metric)
    evidence["scores"] = summarize_scores(evidence["executions"], THRESHOLDS)

    errors = check_evidence(evidence, revision=REVISION)

    assert any(
        f"scores.{metric} scored" in error and "below the approved" in error
        for error in errors
    )
    assert any(f"scores.{metric} did not meet" in error for error in errors)


def test_a_summary_that_contradicts_its_executions_is_refused():
    """The recorded `passed` flags are the vacuous-pass route: every execution failed."""
    evidence = _passing_evidence()
    for item in evidence["executions"]:
        for metric in list(item["metric_results"]):
            _fail_metric(item, metric)

    errors = check_evidence(evidence, revision=REVISION)

    assert "evidence.scores does not match the recorded executions" in errors
    assert any("below the approved" in error for error in errors)


def test_a_hand_written_turn_score_cannot_override_the_retained_evidence():
    evidence = _passing_evidence()
    for item in evidence["executions"]:
        if "english" in item["metric_results"]:
            for turn in item["turns"]:
                turn["score"]["english_passed"] = False

    errors = check_evidence(evidence, revision=REVISION)

    assert any("score does not match recomputed turn evidence" in error for error in errors)
    assert "evidence.scores does not match the recorded executions" not in errors


def test_a_lowered_threshold_is_refused():
    evidence = _passing_evidence()
    evidence["scores"]["hard_invariant"]["threshold"] = 0.5

    assert "evidence.scores does not match the recorded executions" in check_evidence(
        evidence, revision=REVISION
    )


def test_a_metric_with_no_observations_cannot_pass_vacuously():
    evidence = _passing_evidence()
    for item in evidence["executions"]:
        item["metric_results"].pop("safety_boundary", None)
    evidence["scores"] = summarize_scores(evidence["executions"], THRESHOLDS)

    errors = check_evidence(evidence, revision=REVISION)

    assert any("metric_results does not match the authored case" in error for error in errors)


def test_an_unapproved_metric_in_the_executions_is_refused():
    evidence = _passing_evidence()
    evidence["executions"][0]["metric_results"]["invented_metric"] = True

    assert any(
        "metric_results does not match the authored case" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


@pytest.mark.parametrize("status", ["timeout", "skipped", "ok", None])
def test_only_a_completed_execution_counts(status):
    """An allowlist, so an unrecognised or absent status is never read as success."""
    evidence = _passing_evidence()
    if status is None:
        evidence["executions"][5].pop("status")
    else:
        evidence["executions"][5]["status"] = status

    assert any(
        "did not complete" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


def test_execution_passed_flag_must_match_metric_results():
    evidence = _passing_evidence()
    evidence["executions"][9]["passed"] = False

    assert any(
        "passed result contradicts its derived metric results" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


def test_an_execution_without_metric_results_is_refused():
    evidence = _passing_evidence()
    evidence["executions"][3].pop("metric_results")

    assert any(
        "records no metric results" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


@pytest.mark.parametrize("repetitions", [(0, 0, 0), (1, 1, 1), (1, 2, 2), (2, 3, 4)])
def test_three_records_are_not_three_repetitions(repetitions):
    """Counting three rows per case cannot tell repetition 1/2/3 from the same run three times."""
    evidence = _passing_evidence()
    for item in evidence["executions"]:
        if item["case_id"] == "ga-task-01":
            item["repetition"] = repetitions[item["repetition"] - 1]

    assert any(
        "ga-task-01 did not run repetitions 1, 2 and 3" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


def test_an_execution_that_is_not_an_object_is_refused():
    evidence = _passing_evidence()
    evidence["executions"][11] = "looks fine to me"

    assert "every execution must be an object" in check_evidence(evidence, revision=REVISION)


def test_a_run_against_another_model_is_refused():
    evidence = _passing_evidence()
    evidence["release_inputs"]["model"] = "some-other-model"

    assert any(
        "used model 'some-other-model'" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


@pytest.mark.parametrize("repetitions", [3.0, "3", True, None])
def test_the_repetition_count_must_be_the_integer_three(repetitions):
    evidence = _passing_evidence()
    evidence["repetitions"] = repetitions

    assert any(
        "exactly three repetitions" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


def test_non_object_evidence_is_refused():
    assert check_evidence([], revision=REVISION) == ["Gate A evidence must be a JSON object"]


def test_the_checker_exits_non_zero_when_no_run_exists(tmp_path, capsys):
    from scripts.check_gate_a_evidence import main

    missing = tmp_path / "absent.json"
    argv = ["check", "--evidence", str(missing), "--revision", REVISION]
    original = sys.argv
    sys.argv = argv
    try:
        assert main() == 1
    finally:
        sys.argv = original
    assert "no declared Gate A run" in capsys.readouterr().out


def test_unreadable_evidence_is_refused(tmp_path, capsys):
    from scripts.check_gate_a_evidence import main

    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    original = sys.argv
    sys.argv = ["check", "--evidence", str(broken), "--revision", REVISION]
    try:
        assert main() == 1
    finally:
        sys.argv = original
    assert "not readable JSON" in capsys.readouterr().out


def test_non_utf8_evidence_is_refused_without_a_traceback(tmp_path, capsys):
    from scripts.check_gate_a_evidence import main

    broken = tmp_path / "broken.json"
    broken.write_bytes(b"\xff\xfe")
    original = sys.argv
    sys.argv = ["check", "--evidence", str(broken), "--revision", REVISION]
    try:
        assert main() == 1
    finally:
        sys.argv = original
    assert "not readable JSON" in capsys.readouterr().out


def test_the_fixture_matches_the_runner_evidence_shape():
    """Guard against the fixture drifting from what the runner actually writes."""
    runner = (ROOT / "scripts/run_gate_a_eval.py").read_text()
    evidence = _passing_evidence()
    assert set(evidence) == {
        "run_id",
        "suite_id",
        "purpose",
        "declared_at",
        "completed_at",
        "status",
        "environment",
        "minimum_provider_request_interval_seconds",
        "repetitions",
        "selected_cases",
        "release_inputs",
        "pricing",
        "executions",
        "scores",
        "passed",
        "policy",
        "totals",
    }
    for key in evidence:
        if key in {"executions", "scores"}:
            continue
        assert f'"{key}"' in runner, f"runner no longer writes {key}"
    # The execution status string is load-bearing: the checker allowlists it, so a fixture that
    # invents a value the runner never emits would test nothing.
    assert '"status": "completed",' in runner
    assert evidence["executions"][0]["status"] == "completed"
    execution = evidence["executions"][0]
    assert set(execution) == {
        "case_id",
        "category",
        "repetition",
        "observed_model_names",
        "status",
        "passed",
        "metric_results",
        "turns",
        "latency_ms",
        "usage",
        "estimated_cost_usd",
    }
    for key in ("case_id", "repetition", "metric_results", "passed", "latency_ms", "usage"):
        assert f'"{key}"' in runner, f"runner no longer writes execution.{key}"
    calls = sum(
        part["kind"] == "tool_call"
        for item in evidence["executions"]
        for turn in item["turns"]
        for part in turn["trace"]
    )
    results = sum(
        part["kind"] == "tool_result"
        for item in evidence["executions"]
        for turn in item["turns"]
        for part in turn["trace"]
    )
    assert calls == results == 117
    assert json.dumps(evidence)


def _src_import_closure() -> set[str]:
    """Every `src` module a declared run can reach from the modules the runner exercises."""
    def module_path(module: str) -> Path | None:
        direct = ROOT / (module.replace(".", "/") + ".py")
        if direct.is_file():
            return direct
        package = ROOT / module.replace(".", "/") / "__init__.py"
        return package if package.is_file() else None

    seen: set[str] = set()
    pending = list(GATE_A_ENTRY_MODULES)
    while pending:
        module = pending.pop()
        path = module_path(module)
        if path is None or module in seen:
            continue
        seen.add(module)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                if node.module.startswith("src"):
                    pending.append(node.module)
                    pending.extend(f"{node.module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Import):
                pending.extend(alias.name for alias in node.names if alias.name.startswith("src"))
    return {
        str(module_path(module).relative_to(ROOT))
        for module in seen
        if module_path(module) is not None
    }


def test_no_reachable_module_escapes_the_invalidating_fingerprint():
    """A delegated validator must not be able to change behaviour without invalidating a run.

    `file_set_hash` hashes exactly the paths it is handed, so listing `src/memory/store.py` does
    not cover the modules it delegates to. Any new import has to be declared here.
    """
    listed = {path for path in INVALIDATING_INPUT_PATHS if path.startswith("src/")}

    assert _src_import_closure() == listed


def test_every_invalidating_path_exists():
    for relative in INVALIDATING_INPUT_PATHS:
        assert (ROOT / relative).is_file(), f"{relative} is listed but does not exist"


def test_a_configured_alias_is_not_an_observed_model_identity():
    """`gemini-3.5-flash` is a request. Gate A has to record which model actually answered."""
    evidence = _passing_evidence()
    del evidence["release_inputs"]["observed_model_names"]
    assert "evidence.release_inputs.observed_model_names is required" in check_evidence(
        evidence, revision=REVISION
    )


def test_provider_identity_is_derived_from_each_execution():
    evidence = _passing_evidence()
    evidence["executions"][0]["observed_model_names"] = []

    errors = check_evidence(evidence, revision=REVISION)

    assert any("must record exactly one provider-reported model name" in error for error in errors)

    evidence = _passing_evidence()
    evidence["release_inputs"]["observed_model_names"] = ["invented-model-version"]
    assert (
        "evidence.release_inputs.observed_model_names does not match the completed executions"
        in check_evidence(evidence, revision=REVISION)
    )


@pytest.mark.parametrize("invalid", [["model-001", 1], [""], [" model-001"]])
def test_malformed_aggregate_provider_identity_fails_closed(invalid):
    evidence = _passing_evidence()
    evidence["release_inputs"]["observed_model_names"] = invalid

    errors = check_evidence(evidence, revision=REVISION)

    assert any("must contain only nonempty trimmed strings" in error for error in errors)


def test_errored_execution_can_be_recorded_without_a_provider_identity():
    from scripts.run_gate_a_eval import _merge_observed_model_names

    release_inputs = {"observed_model_names": ["model-001"]}
    _merge_observed_model_names(release_inputs, {"status": "error"})

    assert release_inputs["observed_model_names"] == ["model-001"]

    evidence = _passing_evidence()
    evidence["release_inputs"]["observed_model_names"] = []
    assert "evidence.release_inputs.observed_model_names is required" in check_evidence(
        evidence, revision=REVISION
    )


def test_an_alias_that_moved_mid_run_is_not_one_declared_run():
    evidence = _passing_evidence()
    evidence["release_inputs"]["observed_model_names"] = [
        "gemini-3.5-flash-001",
        "gemini-3.5-flash-002",
    ]
    errors = check_evidence(evidence, revision=REVISION)
    assert any("more than one provider model version" in error for error in errors)


def test_a_provider_sdk_upgrade_invalidates_a_declared_run():
    """The SDK sits between the prompt and the model; upgrading it changes behaviour."""
    evidence = _passing_evidence()
    evidence["release_inputs"]["dependency_versions"] = {
        **evidence["release_inputs"]["dependency_versions"],
        "pydantic-ai-slim": "0.0.1-ancient",
    }
    errors = check_evidence(evidence, revision=REVISION)
    assert any("provider/SDK versions changed" in error for error in errors)

    evidence = _passing_evidence()
    del evidence["release_inputs"]["dependency_versions"]
    assert "evidence.release_inputs.dependency_versions is required" in check_evidence(
        evidence, revision=REVISION
    )


def test_the_recorded_sdk_versions_are_the_installed_ones():
    from importlib.metadata import version

    from src.evaluation.gate_a import INVALIDATING_DISTRIBUTIONS, dependency_versions

    recorded = dependency_versions()
    assert set(recorded) == set(INVALIDATING_DISTRIBUTIONS)
    for distribution, recorded_version in recorded.items():
        assert recorded_version == version(distribution)
