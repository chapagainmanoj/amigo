#!/usr/bin/env python3
"""Refuse a declared Gate A run that does not cover the revision it is offered for.

Acceptance criterion 6 of issue 14 requires the complete suite to run again whenever an
invalidating model input changes. Recording fingerprints inside the evidence proves nothing on
its own: a stale run can be attached to a new release by hand. This checker recomputes every
fingerprint from the working tree and rejects the evidence unless the recorded run really is a
complete, passing, three-repetition run of the approved suite against these exact inputs.

It independently rescores complete per-turn trace/response/state evidence, derives execution
metrics and usage/cost totals, and validates the separately hashed last-passing
baseline/comparison. It is fail-closed: a missing, unreadable, partial, aborted, or dev-scoped run
is a failure, and so is an absent evidence file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402
from src.evaluation.gate_a import (  # noqa: E402
    GATE_A_ENVIRONMENT,
    GATE_A_POLICY,
    GATE_A_PRICING,
    PROMPT_SOURCE,
    THRESHOLDS,
    TIME_BEHAVIOR_SOURCES,
    TURN_CONTEXT_SOURCES,
    VALIDATOR_SOURCE,
    build_baseline_comparison,
    canonical_hash,
    dependency_versions,
    execution_metric_results,
    file_set_hash,
    gate_a_state_errors,
    invalidating_inputs,
    load_suite,
    score_turn,
    summarize_scores,
    tool_schema,
)

DEFAULT_SUITE = ROOT / "evals/gate_a/v1/cases.json"
DEFAULT_EVIDENCE = ROOT / "evidence/gate-a/latest.json"
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_REPETITIONS = 3
ARTIFACT_SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ACTOR_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._@-]{2,127}$")
TURN_SCORE_FIELDS = {
    "passed",
    "tool_calls",
    "tool_state_passed",
    "task_extraction_passed",
    "clarification_passed",
    "no_unnecessary_mutation_passed",
    "english_passed",
    "factual_consistency_passed",
    "tone_passed",
    "response_passed",
    "failures",
}
TURN_SCORE_BOOLEAN_FIELDS = TURN_SCORE_FIELDS - {"tool_calls", "failures"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_fingerprints(root: Path, suite_path: Path) -> dict[str, str]:
    """Recompute every invalidating fingerprint from the tree as it stands now."""
    return {
        "prompt_source_sha256": _sha256(root / PROMPT_SOURCE),
        "validator_source_sha256": _sha256(root / VALIDATOR_SOURCE),
        "turn_context_source_sha256": file_set_hash(
            [root / relative for relative in TURN_CONTEXT_SOURCES], root
        ),
        "time_behavior_source_sha256": file_set_hash(
            [root / relative for relative in TIME_BEHAVIOR_SOURCES], root
        ),
        "all_invalidating_inputs_sha256": file_set_hash(invalidating_inputs(root), root),
        "case_set_sha256": _sha256(suite_path),
        "tool_schema_sha256": canonical_hash(tool_schema()),
    }


def _utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        return None
    return parsed.astimezone(UTC)


def _validate_comparison(
    comparison: object,
    *,
    candidate: dict,
    baseline: dict,
    candidate_sha256: object,
    baseline_sha256: object,
    expected_reviewer: str | None,
    review_window_start: datetime | None,
    review_window_end: datetime | None,
    now: datetime,
) -> list[str]:
    """Validate a separately hashed comparison against both run artifacts."""
    if not isinstance(comparison, dict):
        return ["Gate A baseline comparison must be a JSON object"]
    if not isinstance(baseline_sha256, str) or not ARTIFACT_SHA_PATTERN.fullmatch(
        baseline_sha256
    ):
        return ["Gate A baseline artifact SHA-256 is required"]
    if not isinstance(candidate_sha256, str) or not ARTIFACT_SHA_PATTERN.fullmatch(
        candidate_sha256
    ):
        return ["Gate A candidate artifact SHA-256 is required"]

    errors: list[str] = []
    expected = build_baseline_comparison(
        candidate,
        baseline,
        candidate_artifact_sha256=candidate_sha256,
        baseline_artifact_sha256=baseline_sha256,
    )
    for field in (
        "schema_version",
        "baseline",
        "candidate",
        "score_comparison",
        "failure_patterns",
    ):
        if comparison.get(field) != expected[field]:
            errors.append(f"baseline_comparison.{field} does not match the two run artifacts")

    review = comparison.get("human_review")
    if not isinstance(review, dict):
        return [*errors, "baseline_comparison.human_review is required"]
    if review.get("status") != "approved":
        errors.append("baseline comparison human review is not approved")
    reviewer = review.get("reviewer")
    if (
        not isinstance(reviewer, str)
        or reviewer != reviewer.strip().casefold()
        or not ACTOR_ID_PATTERN.fullmatch(reviewer)
    ):
        errors.append(
            "baseline_comparison.human_review.reviewer must be a canonical lowercase "
            "stable actor ID"
        )
    elif expected_reviewer is not None and reviewer != expected_reviewer:
        errors.append(
            "baseline comparison reviewer does not match the model-evaluation evidence reviewer"
        )
    reviewed_at = _utc_timestamp(review.get("reviewed_at"))
    if reviewed_at is None:
        errors.append("baseline_comparison.human_review.reviewed_at must be a UTC timestamp")
    candidate_completed_at = _utc_timestamp(candidate.get("completed_at"))
    if reviewed_at and candidate_completed_at and reviewed_at <= candidate_completed_at:
        errors.append("baseline comparison human review must follow candidate completion")
    if reviewed_at and review_window_start and reviewed_at < review_window_start:
        errors.append("baseline comparison human review predates release evidence collection")
    if reviewed_at and review_window_end and reviewed_at > review_window_end:
        errors.append("baseline comparison human review is after release evidence collection")
    if reviewed_at and reviewed_at > now:
        errors.append("baseline comparison human review cannot be in the future")
    if review.get("baseline_confirmed_last_passing") is not True:
        errors.append("human review must confirm the selected baseline is the last passing run")
    if review.get("tone_reviewed") is not True:
        errors.append("human review must explicitly review the subjective tone results")
    expected_new_ids = [
        pattern["id"] for pattern in expected["failure_patterns"]["new"]
    ]
    if review.get("reviewed_new_failure_pattern_ids") != expected_new_ids:
        errors.append("human review must enumerate every new failure pattern exactly")
    if not isinstance(review.get("notes"), str) or not review["notes"].strip():
        errors.append("baseline comparison human review notes are required")
    return errors


def comparison_reviewed_at(comparison: object) -> datetime | None:
    """Return the comparison's UTC review instant when it is structurally parseable."""
    if not isinstance(comparison, dict) or not isinstance(comparison.get("human_review"), dict):
        return None
    return _utc_timestamp(comparison["human_review"].get("reviewed_at"))


def _validate_trace(
    trace: object, *, known_tools: set[str], label: str, errors: list[str]
) -> bool:
    """Validate the ordered call/result stream emitted by pydantic-ai."""
    if not isinstance(trace, list):
        errors.append(f"{label}.trace must be a list of trace objects")
        return False
    valid = True
    outstanding: dict[str, str] = {}
    for index, part in enumerate(trace):
        part_label = f"{label}.trace[{index}]"
        if not isinstance(part, dict):
            errors.append(f"{part_label} must be an object")
            valid = False
            continue
        kind = part.get("kind")
        if not isinstance(kind, str) or kind not in ("tool_call", "tool_result"):
            errors.append(f"{part_label}.kind is invalid")
            valid = False
            continue
        tool = part.get("tool")
        tool_valid = (
            isinstance(tool, str) and bool(tool.strip()) and tool in known_tools
        )
        if not tool_valid:
            errors.append(f"{part_label}.tool must name a known Gate A Tool")
            valid = False
        call_id = part.get("call_id")
        call_id_valid = isinstance(call_id, str) and bool(call_id.strip())
        if not call_id_valid:
            errors.append(f"{part_label}.call_id must be nonempty")
            valid = False
        if kind == "tool_call":
            if set(part) != {"kind", "tool", "call_id", "args"} or not isinstance(
                part.get("args"), (dict, str)
            ):
                errors.append(f"{part_label} is not a valid Tool call")
                valid = False
            elif tool_valid and call_id_valid:
                if call_id in outstanding:
                    errors.append(f"{part_label}.call_id is duplicated")
                    valid = False
                else:
                    outstanding[call_id] = tool
        else:
            content = part.get("content")
            if (
                set(part) != {"kind", "tool", "call_id", "content"}
                or not isinstance(content, str)
                or not content.strip()
                or len(content) > 2_000
            ):
                errors.append(f"{part_label} is not a valid Tool result")
                valid = False
            if tool_valid and call_id_valid:
                expected_tool = outstanding.get(call_id)
                if expected_tool is None:
                    errors.append(f"{part_label} is an orphan Tool result")
                    valid = False
                elif expected_tool != tool:
                    errors.append(f"{part_label}.tool does not match its Tool call")
                    valid = False
                else:
                    del outstanding[call_id]
    unmatched = sorted(outstanding)
    if unmatched:
        errors.append(f"{label}.trace has Tool calls without matching result IDs: {unmatched}")
        valid = False
    return valid


def _validate_execution_aggregates(
    item: dict, *, label: str, errors: list[str]
) -> dict | None:
    """Recompute execution usage and cost from its retained turn records."""
    turns = item.get("turns")
    if not isinstance(turns, list):
        return None
    input_tokens = 0
    output_tokens = 0
    turn_latency = 0.0
    valid = True
    for index, turn in enumerate(turns, start=1):
        turn_label = f"{label} turn {index}"
        if not isinstance(turn, dict):
            valid = False
            continue
        latency = turn.get("latency_ms")
        if not isinstance(latency, (int, float)) or isinstance(latency, bool) or latency < 0:
            errors.append(f"{turn_label}.latency_ms must be nonnegative")
            valid = False
        else:
            turn_latency += latency
        usage = turn.get("usage")
        usage_fields = {
            "requests",
            "tool_calls",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "details",
        }
        if not isinstance(usage, dict) or set(usage) != usage_fields:
            errors.append(f"{turn_label}.usage is incomplete")
            valid = False
            continue
        if any(
            type(usage.get(field)) is not int or usage[field] < 0
            for field in usage_fields - {"details"}
        ) or not isinstance(usage.get("details"), dict):
            errors.append(f"{turn_label}.usage values are invalid")
            valid = False
            continue
        trace = turn.get("trace")
        trace_call_count = (
            sum(
                isinstance(part, dict) and part.get("kind") == "tool_call"
                for part in trace
            )
            if isinstance(trace, list)
            else None
        )
        if trace_call_count is not None and usage["tool_calls"] != trace_call_count:
            errors.append(f"{turn_label}.usage.tool_calls does not match its trace")
            valid = False
        input_tokens += usage["input_tokens"]
        output_tokens += usage["output_tokens"]

    aggregate_latency = item.get("latency_ms")
    if (
        not isinstance(aggregate_latency, (int, float))
        or isinstance(aggregate_latency, bool)
        or aggregate_latency < turn_latency
    ):
        errors.append(f"{label}.latency_ms must cover its turn latencies")
        valid = False
    aggregate_usage = item.get("usage")
    expected_usage = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if (
        not isinstance(aggregate_usage, dict)
        or set(aggregate_usage) != set(expected_usage)
        or any(
            type(aggregate_usage.get(field)) is not int or aggregate_usage[field] < 0
            for field in expected_usage
        )
        or aggregate_usage != expected_usage
    ):
        errors.append(f"{label}.usage does not match its turn usage")
        valid = False
    expected_cost = round(
        (
            input_tokens * GATE_A_PRICING["input_per_million_tokens"]
            + output_tokens * GATE_A_PRICING["output_per_million_tokens"]
        )
        / 1_000_000,
        8,
    )
    cost = item.get("estimated_cost_usd")
    if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost != expected_cost:
        errors.append(f"{label}.estimated_cost_usd does not match its turn usage")
        valid = False
    if not valid:
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": expected_cost,
    }


def _derive_execution_metrics(
    item: dict,
    case,
    label: str,
    errors: list[str],
    *,
    known_tools: set[str],
) -> dict | None:
    """Recompute turn scores and derive metrics from retained execution evidence."""
    turns = item.get("turns")
    if not isinstance(turns, list) or len(turns) != len(case.turns):
        errors.append(f"{label} must record every authored turn")
        return None
    turn_scores = []
    prior_state_hash = None
    for index, (recorded, authored) in enumerate(zip(turns, case.turns, strict=True), start=1):
        turn_label = f"{label} turn {index}"
        if not isinstance(recorded, dict):
            errors.append(f"{turn_label} must be an object")
            continue
        if recorded.get("turn") != index:
            errors.append(f"{turn_label}.turn must equal {index}")
        if recorded.get("message") != authored.message:
            errors.append(f"{turn_label}.message does not match the authored case")
        before_state_hash = recorded.get("before_state_hash")
        before_state_valid = (
            isinstance(before_state_hash, str)
            and bool(ARTIFACT_SHA_PATTERN.fullmatch(before_state_hash))
        )
        if not before_state_valid:
            errors.append(f"{turn_label}.before_state_hash must be a lowercase SHA-256 digest")
        elif prior_state_hash is not None and before_state_hash != prior_state_hash:
            errors.append(f"{turn_label}.before_state_hash does not chain the prior turn")
            before_state_valid = False
        trace = recorded.get("trace")
        trace_valid = _validate_trace(
            trace, known_tools=known_tools, label=turn_label, errors=errors
        )
        response = recorded.get("response")
        response_valid = isinstance(response, str)
        if not response_valid:
            errors.append(f"{turn_label}.response must be a string")
        state = recorded.get("state")
        state_errors = gate_a_state_errors(state)
        state_valid = not state_errors
        errors.extend(f"{turn_label}.state {reason}" for reason in state_errors)
        if isinstance(state, dict) and isinstance(state.get("state_hash"), str):
            prior_state_hash = state["state_hash"]
        else:
            prior_state_hash = None
        recorded_score = recorded.get("score")
        score_valid = isinstance(recorded_score, dict) and set(recorded_score) == TURN_SCORE_FIELDS
        if not score_valid:
            errors.append(f"{turn_label}.score does not match the scorer contract")
        elif any(
            not isinstance(recorded_score.get(field), bool)
            for field in TURN_SCORE_BOOLEAN_FIELDS
        ):
            errors.append(f"{turn_label}.score boolean results are invalid")
            score_valid = False
        elif (
            not isinstance(recorded_score.get("tool_calls"), dict)
            or any(
                not isinstance(tool, str)
                or type(count) is not int
                or count < 0
                for tool, count in recorded_score.get("tool_calls", {}).items()
            )
            or not isinstance(recorded_score.get("failures"), list)
            or any(
                not isinstance(failure, str)
                for failure in recorded_score.get("failures", [])
            )
        ):
            errors.append(f"{turn_label}.score trace summary is invalid")
            score_valid = False

        if not (before_state_valid and trace_valid and response_valid and state_valid):
            continue
        try:
            recomputed_score = score_turn(
                authored,
                trace=trace,
                response=response,
                state=state,
                before_state_hash=before_state_hash,
            )
        except (KeyError, TypeError, ValueError) as error:
            errors.append(f"{turn_label} cannot be rescored: {error}")
            continue
        if not score_valid or recorded_score != recomputed_score:
            errors.append(f"{turn_label}.score does not match recomputed turn evidence")
        turn_scores.append(recomputed_score)
    if len(turn_scores) != len(case.turns):
        return None
    return execution_metric_results(case, turn_scores)


def check_evidence(
    evidence: object,
    *,
    revision: str,
    root: Path = ROOT,
    suite_path: Path = DEFAULT_SUITE,
    baseline_evidence: object | None = None,
    candidate_sha256: str | None = None,
    baseline_sha256: str | None = None,
    comparison: object | None = None,
    expected_reviewer: str | None = None,
    review_window_start: datetime | None = None,
    review_window_end: datetime | None = None,
    now: datetime | None = None,
    _historical_baseline: bool = False,
) -> list[str]:
    """Return every reason this evidence cannot stand for ``revision``; empty means it can."""
    errors: list[str] = []
    if not isinstance(evidence, dict):
        return ["Gate A evidence must be a JSON object"]
    if not isinstance(revision, str) or not REVISION_PATTERN.fullmatch(revision):
        errors.append("revision must be a full lowercase Git commit SHA")

    suite = load_suite(suite_path)
    cases_by_id = {case.id: case for case in suite.cases}
    current_tool_schema = tool_schema()
    known_tools = {item["name"] for item in current_tool_schema}
    if evidence.get("suite_id") != suite.suite_id:
        errors.append(f"evidence.suite_id must be {suite.suite_id}")
    if _historical_baseline:
        if evidence.get("purpose") not in {"baseline", "release_candidate"}:
            errors.append("historical baseline must be a declared full-run artifact")
    elif evidence.get("purpose") != "release_candidate":
        errors.append("Gate A release evidence must have purpose release_candidate")
    if evidence.get("status") != "passed" or evidence.get("passed") is not True:
        errors.append(f"the declared run did not pass: status={evidence.get('status')!r}")
    if evidence.get("environment") != GATE_A_ENVIRONMENT:
        errors.append(f"evidence.environment must be {GATE_A_ENVIRONMENT}")
    request_interval = evidence.get("minimum_provider_request_interval_seconds")
    if (
        not isinstance(request_interval, (int, float))
        or isinstance(request_interval, bool)
        or request_interval < 0
    ):
        errors.append("evidence.minimum_provider_request_interval_seconds is invalid")
    if evidence.get("pricing") != GATE_A_PRICING:
        errors.append("evidence.pricing does not match the approved pricing snapshot")
    if evidence.get("policy") != GATE_A_POLICY:
        errors.append("evidence.policy does not match the declared-run retry policy")
    if evidence.get("repetitions") is not REQUIRED_REPETITIONS:
        errors.append("a declared run must use exactly three repetitions")
    if evidence.get("provider_incidents"):
        errors.append("the declared run recorded a provider incident and is not release evidence")
    if not isinstance(evidence.get("run_id"), str) or not evidence["run_id"].strip():
        errors.append("evidence.run_id is required")
    declared_at = _utc_timestamp(evidence.get("declared_at"))
    completed_at = _utc_timestamp(evidence.get("completed_at"))
    if declared_at is None:
        errors.append("evidence.declared_at must be a UTC timestamp")
    if completed_at is None:
        errors.append("evidence.completed_at must be a UTC timestamp")
    if declared_at and completed_at and completed_at <= declared_at:
        errors.append("evidence.completed_at must follow evidence.declared_at")

    expected_ids = sorted(case.id for case in suite.cases)
    selected_cases = evidence.get("selected_cases")
    if (
        not isinstance(selected_cases, list)
        or any(not isinstance(case_id, str) for case_id in selected_cases)
        or sorted(selected_cases) != expected_ids
    ):
        errors.append("a declared run must select every approved case, not a development subset")

    executions = evidence.get("executions")
    if not isinstance(executions, list):
        errors.append("evidence.executions is required")
        executions = []
    expected_executions = len(expected_ids) * REQUIRED_REPETITIONS
    if len(executions) != expected_executions:
        errors.append(
            f"expected {expected_executions} executions, found {len(executions)}"
        )
    # Repetitions are checked by identity, not by count: three records of repetition 1 is not
    # "every case three times", and a count alone cannot tell the difference.
    repetitions_by_case: dict[object, set] = defaultdict(set)
    execution_keys: set[tuple[str, int]] = set()
    scored: list[dict] = []
    run_aggregates: list[dict] = []
    execution_model_names: set[str] = set()
    for item in executions:
        if not isinstance(item, dict):
            errors.append("every execution must be an object")
            continue
        case_id = item.get("case_id")
        if not isinstance(case_id, str):
            errors.append("every execution must record a string case_id")
        repetition = item.get("repetition")
        if type(repetition) is not int or repetition not in range(1, REQUIRED_REPETITIONS + 1):
            errors.append(
                f"{case_id} repetition must be a non-boolean integer from 1 through 3"
            )
        elif isinstance(case_id, str):
            execution_key = (case_id, repetition)
            if execution_key in execution_keys:
                errors.append(f"{case_id} repetition {repetition} is duplicated")
            execution_keys.add(execution_key)
            repetitions_by_case[case_id].add(repetition)
        # An allowlist, not a denylist: an unrecognised or absent status is not a success.
        if item.get("status") != "completed":
            errors.append(
                f"{item.get('case_id')} repetition {item.get('repetition')} "
                "did not complete"
            )
        if not isinstance(item.get("passed"), bool):
            errors.append(
                f"{item.get('case_id')} repetition {item.get('repetition')} "
                "must record a boolean passed result"
            )
        metric_results = item.get("metric_results")
        if not isinstance(metric_results, dict):
            errors.append(
                f"{item.get('case_id')} repetition {item.get('repetition')} "
                "records no metric results"
            )
        elif any(not isinstance(passed, bool) for passed in metric_results.values()):
            errors.append(
                f"{item.get('case_id')} repetition {item.get('repetition')} "
                "metric results must be booleans"
            )
        case = cases_by_id.get(case_id) if isinstance(case_id, str) else None
        label = f"{case_id} repetition {repetition}"
        if case is None:
            errors.append(f"{label} does not name an authored Gate A case")
        else:
            if item.get("category") != case.category:
                errors.append(f"{label}.category does not match the authored case")
            expected_metrics = set(case.metrics)
            if not isinstance(metric_results, dict) or set(metric_results) != expected_metrics:
                errors.append(f"{label}.metric_results does not match the authored case")
            derived_metrics = _derive_execution_metrics(
                item, case, label, errors, known_tools=known_tools
            )
            if derived_metrics is not None:
                if metric_results != derived_metrics:
                    errors.append(f"{label}.metric_results does not match its turn evidence")
                derived_item = {**item, "metric_results": derived_metrics}
                scored.append(derived_item)
                if isinstance(item.get("passed"), bool) and item["passed"] is not all(
                    derived_metrics.values()
                ):
                    errors.append(
                        f"{label} passed result contradicts its derived metric results"
                    )
            elif isinstance(item.get("passed"), bool) and item["passed"] is not all(
                metric_results.values() if isinstance(metric_results, dict) else ()
            ):
                errors.append(
                    f"{label} passed result contradicts its recorded metric results"
                )
        aggregate = _validate_execution_aggregates(item, label=label, errors=errors)
        if aggregate is not None:
            run_aggregates.append(aggregate)
        model_names = item.get("observed_model_names")
        if (
            not isinstance(model_names, list)
            or len(model_names) != 1
            or not isinstance(model_names[0], str)
            or not model_names[0]
            or model_names[0] != model_names[0].strip()
        ):
            errors.append(
                f"{item.get('case_id')} repetition {item.get('repetition')} must record "
                "exactly one provider-reported model name"
            )
        else:
            execution_model_names.add(model_names[0])
    for case_id in expected_ids:
        observed = sorted(str(value) for value in repetitions_by_case.get(case_id, ()))
        if repetitions_by_case.get(case_id) != set(range(1, REQUIRED_REPETITIONS + 1)):
            errors.append(f"{case_id} did not run repetitions 1, 2 and 3 (found {observed})")

    release_inputs = evidence.get("release_inputs")
    if not isinstance(release_inputs, dict):
        errors.append("evidence.release_inputs is required")
        release_inputs = {}
    if release_inputs.get("git_revision") != revision:
        errors.append(
            "the declared run was executed against "
            f"{release_inputs.get('git_revision')!r}, not {revision!r}"
        )
    if release_inputs.get("working_tree_dirty") is not False:
        errors.append("the declared run was executed from a dirty working tree")
    empty_diff_sha256 = hashlib.sha256(b"").hexdigest()
    if release_inputs.get("working_tree_diff_sha256") != empty_diff_sha256:
        errors.append("evidence.release_inputs.working_tree_diff_sha256 must prove a clean tree")
    if not _historical_baseline and release_inputs.get("model") != settings.default_model:
        errors.append(
            f"the declared run used model {release_inputs.get('model')!r}, "
            f"not the configured {settings.default_model!r}"
        )
    elif _historical_baseline and (
        not isinstance(release_inputs.get("model"), str)
        or not release_inputs["model"].strip()
    ):
        errors.append("historical baseline release_inputs.model is required")
    expected_provider_model = (
        f"google:{settings.default_model}"
        if settings.default_model.startswith("gemini-")
        else settings.default_model
    )
    provider_model = release_inputs.get("provider_model")
    if _historical_baseline:
        if not isinstance(provider_model, str) or not provider_model.strip():
            errors.append("historical baseline release_inputs.provider_model is required")
    elif provider_model != expected_provider_model:
        errors.append("evidence.release_inputs.provider_model does not match the release model")
    if release_inputs.get("model_settings") != {}:
        errors.append("evidence.release_inputs.model_settings must match the runner settings")
    if (
        type(release_inputs.get("case_set_version")) is not int
        or release_inputs["case_set_version"] != suite.version
    ):
        errors.append("evidence.release_inputs.case_set_version does not match the suite")
    if release_inputs.get("fixed_utc") != suite.fixed_utc:
        errors.append("evidence.release_inputs.fixed_utc does not match the suite")
    if release_inputs.get("timezone") != suite.timezone:
        errors.append("evidence.release_inputs.timezone does not match the suite")
    recorded_tool_schema = release_inputs.get("tool_schema")
    if not isinstance(recorded_tool_schema, list):
        errors.append("evidence.release_inputs.tool_schema is required")
    else:
        recorded_schema_hash = canonical_hash(recorded_tool_schema)
        if recorded_schema_hash != release_inputs.get("tool_schema_sha256"):
            errors.append("evidence.release_inputs.tool_schema does not match its SHA-256")
        if not _historical_baseline and recorded_tool_schema != current_tool_schema:
            errors.append("evidence.release_inputs.tool_schema does not match the current Tools")
    # The configured alias only names what was asked for. Gate A evidence has to say which model
    # actually answered, and an alias that resolved to two different versions mid-run was not one
    # declared run against one model.
    observed = release_inputs.get("observed_model_names")
    if not isinstance(observed, list) or not observed:
        errors.append("evidence.release_inputs.observed_model_names is required")
    elif any(
        not isinstance(name, str) or not name or name != name.strip()
        for name in observed
    ):
        errors.append(
            "evidence.release_inputs.observed_model_names must contain only "
            "nonempty trimmed strings"
        )
    elif len(observed) > 1:
        errors.append(
            f"the declared run spanned more than one provider model version: {sorted(observed)}"
        )
    if (
        isinstance(observed, list)
        and all(isinstance(name, str) for name in observed)
        and sorted(observed) != sorted(execution_model_names)
    ):
        errors.append(
            "evidence.release_inputs.observed_model_names does not match the completed executions"
        )
    recorded_versions = release_inputs.get("dependency_versions")
    if not isinstance(recorded_versions, dict) or not recorded_versions:
        errors.append("evidence.release_inputs.dependency_versions is required")
    elif not _historical_baseline:
        current_versions = dependency_versions()
        drifted = sorted(
            name
            for name in set(current_versions) | set(recorded_versions)
            if recorded_versions.get(name) != current_versions.get(name)
        )
        if drifted:
            errors.append(
                f"provider/SDK versions changed since the declared run: {drifted}; "
                "Gate A must run again"
            )

    fingerprints = current_fingerprints(root, suite_path)
    for name, expected in fingerprints.items():
        recorded = release_inputs.get(name)
        if _historical_baseline:
            if not isinstance(recorded, str) or not ARTIFACT_SHA_PATTERN.fullmatch(recorded):
                errors.append(f"historical baseline release_inputs.{name} is invalid")
        elif recorded != expected:
            errors.append(
                f"{name} changed since the declared run "
                f"(recorded {recorded!r}, current {expected!r}); Gate A must run again"
            )

    totals = evidence.get("totals")
    expected_totals = {
        "executions": len(executions),
        "input_tokens": sum(item["input_tokens"] for item in run_aggregates),
        "output_tokens": sum(item["output_tokens"] for item in run_aggregates),
        "estimated_cost_usd": round(
            sum(item["estimated_cost_usd"] for item in run_aggregates), 8
        ),
    }
    totals_valid = (
        isinstance(totals, dict)
        and set(totals) == set(expected_totals)
        and all(
            type(totals.get(field)) is int and totals[field] >= 0
            for field in ("executions", "input_tokens", "output_tokens")
        )
        and isinstance(totals.get("estimated_cost_usd"), (int, float))
        and not isinstance(totals.get("estimated_cost_usd"), bool)
        and totals["estimated_cost_usd"] >= 0
    )
    if (
        len(run_aggregates) != len(executions)
        or not totals_valid
        or totals != expected_totals
    ):
        errors.append("evidence.totals does not match the retained executions")

    scores = evidence.get("scores")
    if not isinstance(scores, dict):
        errors.append("evidence.scores is required")
        scores = {}
    for metric in set(scores) - set(THRESHOLDS):
        errors.append(f"scores.{metric} is not an approved Gate A metric")

    # The recorded summary is derived, not trusted: a `passed` flag someone typed is no evidence.
    # Recomputing it from the executions is the only thing that ties the verdict to the run.
    unknown = {
        metric
        for item in scored
        for metric in item["metric_results"]
        if metric not in THRESHOLDS
    }
    if unknown:
        errors.append(f"executions record unapproved metrics: {sorted(unknown)}")
    elif not errors or scored:
        recomputed = summarize_scores(scored, THRESHOLDS)
        if scores != recomputed:
            errors.append("evidence.scores does not match the recorded executions")
        derived_pass = all(result["passed"] for result in recomputed.values())
        if evidence.get("passed") is not derived_pass or evidence.get("status") != (
            "passed" if derived_pass else "failed"
        ):
            errors.append("evidence status does not match the recomputed category scores")
        for metric, threshold in THRESHOLDS.items():
            result = recomputed[metric]
            if not result["observations"]:
                errors.append(f"scores.{metric} has no observations")
            elif result["score"] < threshold:
                errors.append(
                    f"scores.{metric} scored {result['score']} "
                    f"below the approved {threshold}"
                )
            if not result["passed"]:
                errors.append(f"scores.{metric} did not meet its approved threshold")

    if _historical_baseline:
        return errors

    if not isinstance(baseline_evidence, dict):
        errors.append("the archived last-passing Gate A baseline artifact is required")
    else:
        baseline_inputs = baseline_evidence.get("release_inputs")
        baseline_revision = (
            baseline_inputs.get("git_revision") if isinstance(baseline_inputs, dict) else None
        )
        if not isinstance(baseline_revision, str) or not REVISION_PATTERN.fullmatch(
            baseline_revision
        ):
            errors.append("historical baseline git revision is invalid")
        else:
            for reason in check_evidence(
                baseline_evidence,
                revision=baseline_revision,
                root=root,
                suite_path=suite_path,
                now=now,
                _historical_baseline=True,
            ):
                errors.append(f"historical baseline: {reason}")
        if baseline_evidence.get("run_id") == evidence.get("run_id"):
            errors.append("candidate and historical baseline must be distinct declared runs")
        baseline_completed_at = _utc_timestamp(baseline_evidence.get("completed_at"))
        candidate_declared_at = _utc_timestamp(evidence.get("declared_at"))
        if (
            baseline_completed_at
            and candidate_declared_at
            and baseline_completed_at >= candidate_declared_at
        ):
            errors.append("historical baseline must predate candidate declaration")
        errors.extend(
            _validate_comparison(
                comparison,
                candidate=evidence,
                baseline=baseline_evidence,
                candidate_sha256=candidate_sha256,
                baseline_sha256=baseline_sha256,
                expected_reviewer=expected_reviewer,
                review_window_start=review_window_start,
                review_window_end=review_window_end,
                now=(now or datetime.now(UTC)).astimezone(UTC),
            )
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Archived full JSON artifact for the last passing Gate A run",
    )
    parser.add_argument(
        "--comparison",
        type=Path,
        help="Generated candidate/baseline comparison with completed human review",
    )
    parser.add_argument("--revision", required=True, help="The exact release Git SHA")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    args = parser.parse_args()

    if not args.evidence.is_file():
        print(f"FAIL: no declared Gate A run at {args.evidence}")
        return 1
    try:
        evidence_bytes = args.evidence.read_bytes()
        evidence = json.loads(evidence_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        print(f"FAIL: {args.evidence} is not readable JSON: {error}")
        return 1

    for label, path in (("baseline", args.baseline), ("comparison", args.comparison)):
        if path is None or not path.is_file():
            print(f"FAIL: no Gate A {label} artifact at {path}")
            return 1
    try:
        baseline_bytes = args.baseline.read_bytes()
        baseline = json.loads(baseline_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        print(f"FAIL: {args.baseline} is not readable JSON: {error}")
        return 1
    try:
        comparison = json.loads(args.comparison.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as error:
        print(f"FAIL: {args.comparison} is not readable JSON: {error}")
        return 1

    errors = check_evidence(
        evidence,
        revision=args.revision,
        root=ROOT,
        suite_path=args.suite.resolve(),
        baseline_evidence=baseline,
        candidate_sha256=hashlib.sha256(evidence_bytes).hexdigest(),
        baseline_sha256=hashlib.sha256(baseline_bytes).hexdigest(),
        comparison=comparison,
    )
    if errors:
        print(f"FAIL: the declared Gate A run cannot stand for {args.revision}")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"ok: a complete passing Gate A run covers {args.revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
