"""A declared Gate A run must not be presentable as evidence for a tree it never ran against."""

import ast
import json
import sys
from pathlib import Path

import pytest

from scripts.check_gate_a_evidence import ROOT, check_evidence
from src.evaluation.gate_a import (
    GATE_A_ENTRY_MODULES,
    INVALIDATING_INPUT_PATHS,
    THRESHOLDS,
    summarize_scores,
)
from tests.gate_a_fixtures import passing_gate_a_evidence

REVISION = "0" * 39 + "a"


def _passing_evidence() -> dict:
    return passing_gate_a_evidence(REVISION)


def test_a_complete_passing_run_against_this_tree_is_accepted():
    assert check_evidence(_passing_evidence(), revision=REVISION) == []


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
        "did not complete and pass" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


@pytest.mark.parametrize("metric", sorted(THRESHOLDS))
def test_every_metric_must_meet_its_approved_threshold(metric):
    """Fail the metric in the executions themselves, not in the recorded summary."""
    evidence = _passing_evidence()
    for item in evidence["executions"]:
        if metric in item["metric_results"]:
            item["metric_results"][metric] = False
    evidence["scores"] = summarize_scores(evidence["executions"], THRESHOLDS)

    errors = check_evidence(evidence, revision=REVISION)

    assert any(f"scores.{metric} scored 0.0 below the approved" in error for error in errors)
    assert any(f"scores.{metric} did not meet" in error for error in errors)


def test_a_summary_that_contradicts_its_executions_is_refused():
    """The recorded `passed` flags are the vacuous-pass route: every execution failed."""
    evidence = _passing_evidence()
    for item in evidence["executions"]:
        item["passed"] = False
        item["metric_results"] = dict.fromkeys(item["metric_results"], False)

    errors = check_evidence(evidence, revision=REVISION)

    assert "evidence.scores does not match the recorded executions" in errors
    assert any("did not complete and pass" in error for error in errors)


def test_a_hand_written_passing_summary_cannot_override_the_run():
    evidence = _passing_evidence()
    for item in evidence["executions"]:
        item["metric_results"]["english"] = False

    errors = check_evidence(evidence, revision=REVISION)

    assert "evidence.scores does not match the recorded executions" in errors


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

    assert any("scores.safety_boundary has no observations" in error for error in errors)


def test_an_unapproved_metric_in_the_executions_is_refused():
    evidence = _passing_evidence()
    evidence["executions"][0]["metric_results"]["invented_metric"] = True

    assert any(
        "executions record unapproved metrics" in error
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
        "did not complete and pass" in error
        for error in check_evidence(evidence, revision=REVISION)
    )


def test_an_execution_that_did_not_pass_is_refused():
    evidence = _passing_evidence()
    evidence["executions"][9]["passed"] = False

    assert any(
        "did not complete and pass" in error
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


def test_the_fixture_matches_the_runner_evidence_shape():
    """Guard against the fixture drifting from what the runner actually writes."""
    runner = (ROOT / "scripts/run_gate_a_eval.py").read_text()
    evidence = _passing_evidence()
    for key in evidence:
        if key in {"executions", "scores"}:
            continue
        assert f'"{key}"' in runner, f"runner no longer writes {key}"
    # The execution status string is load-bearing: the checker allowlists it, so a fixture that
    # invents a value the runner never emits would test nothing.
    assert '"status": "completed",' in runner
    assert evidence["executions"][0]["status"] == "completed"
    for key in ("case_id", "repetition", "metric_results", "passed", "latency_ms", "usage"):
        assert f'"{key}"' in runner, f"runner no longer writes execution.{key}"
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
