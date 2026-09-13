"""One builder for a complete, passing declared Gate A run.

Shared so the currency checker and the release-evidence manifest are tested against the same
shape `scripts/run_gate_a_eval.py` actually writes — including the execution ``status`` string
the runner really emits, which an earlier hand-written fixture got wrong.
"""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from scripts.check_gate_a_evidence import ROOT, current_fingerprints
from src.config import settings
from src.evaluation.gate_a import (
    GATE_A_ENVIRONMENT,
    GATE_A_POLICY,
    GATE_A_PRICING,
    THRESHOLDS,
    build_baseline_comparison,
    dependency_versions,
    execution_metric_results,
    gate_a_state_hash,
    load_suite,
    score_turn,
    summarize_scores,
    tool_schema,
)

SUITE_PATH: Path = ROOT / "evals/gate_a/v1/cases.json"


def _passing_turn_evidence(
    case, turn, turn_index: int, prior_state: dict | None
) -> dict:
    """Build retained evidence that the production scorer independently accepts."""
    trace = []
    for tool, expected_count in turn.expected_tools.items():
        count = expected_count if isinstance(expected_count, int) else expected_count.minimum
        for _ in range(count):
            call_id = f"{case.id}-{turn_index}-call-{len(trace) + 1}"
            trace.append(
                {"kind": "tool_call", "tool": tool, "call_id": call_id, "args": {}}
            )
    trace.extend(
        {
            "kind": "tool_result",
            "tool": item["tool"],
            "call_id": item["call_id"],
            "content": "{}",
        }
        for item in list(trace)
    )

    required_phrases = [*turn.response.must_include_all]
    if turn.response.must_include_any:
        required_phrases.append(turn.response.must_include_any[0])
    response = " ".join([*required_phrases, "Okay"])
    response += "?" if turn.response.question_required else "."

    expected_state = turn.expected_state
    task_count = expected_state.task_count or 0
    titles = list(expected_state.task_titles_contain)
    tasks = [
        {
            "task_id": f"{case.id}-task-{index + 1}",
            "title": titles[index] if index < len(titles) else f"Fixture task {index + 1}",
            "status": "pending",
            "due_date": None,
            "version": 1,
        }
        for index in range(task_count)
    ]
    aliases = {}
    alias_names = sorted(
        set(expected_state.task_statuses) | set(expected_state.task_due_dates)
    )
    for index, alias in enumerate(alias_names):
        task = tasks[min(index, len(tasks) - 1)]
        task["status"] = expected_state.task_statuses.get(alias, task["status"])
        task["due_date"] = expected_state.task_due_dates.get(alias, task["due_date"])
        aliases[alias] = task
    reminders = [
        {
            "reminder_id": f"{case.id}-reminder-{index + 1}",
            "task_id": tasks[min(index, len(tasks) - 1)]["task_id"],
            "status": "pending",
            "scheduled_time": f"2026-09-02T0{index}:00:00+00:00",
        }
        for index in range(expected_state.pending_reminder_count or 0)
    ]
    state = {
        "tasks": tasks,
        "pending_reminders": reminders,
        "aliases": aliases,
    }
    state["state_hash"] = gate_a_state_hash(tasks, reminders, aliases)
    if expected_state.unchanged and prior_state is not None:
        state = deepcopy(prior_state)
    before_state_hash = (
        prior_state["state_hash"] if prior_state is not None else state["state_hash"]
    )
    score = score_turn(
        turn,
        trace=trace,
        response=response,
        state=state,
        before_state_hash=before_state_hash,
    )
    assert score["passed"], score["failures"]
    return {
        "turn": turn_index,
        "message": turn.message,
        "before_state_hash": before_state_hash,
        "trace": trace,
        "response": response,
        "state": state,
        "latency_ms": 1.0,
        "usage": {
            "requests": 1,
            "tool_calls": sum(item["kind"] == "tool_call" for item in trace),
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "details": {},
        },
        "score": score,
    }


def _passing_execution(case, repetition: int) -> dict:
    turns = []
    prior_state = None
    for turn_index, turn in enumerate(case.turns, start=1):
        evidence = _passing_turn_evidence(case, turn, turn_index, prior_state)
        turns.append(evidence)
        prior_state = evidence["state"]
    metric_results = execution_metric_results(case, [turn["score"] for turn in turns])
    input_tokens = sum(turn["usage"]["input_tokens"] for turn in turns)
    output_tokens = sum(turn["usage"]["output_tokens"] for turn in turns)
    cost = round(
        (
            input_tokens * GATE_A_PRICING["input_per_million_tokens"]
            + output_tokens * GATE_A_PRICING["output_per_million_tokens"]
        )
        / 1_000_000,
        8,
    )
    return {
        "case_id": case.id,
        "category": case.category,
        "repetition": repetition,
        "status": "completed",
        "passed": all(metric_results.values()),
        "observed_model_names": [f"{settings.default_model}-001"],
        "metric_results": metric_results,
        "latency_ms": 1200,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "estimated_cost_usd": cost,
        "turns": turns,
    }


def passing_gate_a_evidence(revision: str) -> dict:
    suite = load_suite(SUITE_PATH)
    executions = [
        _passing_execution(case, repetition)
        for case in suite.cases
        for repetition in (1, 2, 3)
    ]
    schema = tool_schema()
    totals = {
        "executions": len(executions),
        "input_tokens": sum(item["usage"]["input_tokens"] for item in executions),
        "output_tokens": sum(item["usage"]["output_tokens"] for item in executions),
        "estimated_cost_usd": round(
            sum(item["estimated_cost_usd"] for item in executions), 8
        ),
    }
    return {
        "run_id": "11111111-1111-4111-8111-111111111111",
        "suite_id": suite.suite_id,
        "purpose": "release_candidate",
        "status": "passed",
        "passed": True,
        "declared_at": "2026-09-02T01:01:00+00:00",
        "completed_at": "2026-09-02T01:05:00+00:00",
        "environment": GATE_A_ENVIRONMENT,
        "minimum_provider_request_interval_seconds": 13.0,
        "repetitions": 3,
        "selected_cases": [case.id for case in suite.cases],
        "release_inputs": {
            "git_revision": revision,
            "working_tree_dirty": False,
            "working_tree_diff_sha256": hashlib.sha256(b"").hexdigest(),
            "model": settings.default_model,
            "provider_model": (
                f"google:{settings.default_model}"
                if settings.default_model.startswith("gemini-")
                else settings.default_model
            ),
            # The runner records what the provider reported, not the configured alias.
            "observed_model_names": [f"{settings.default_model}-001"],
            "model_settings": {},
            "dependency_versions": dependency_versions(),
            "tool_schema": schema,
            "case_set_version": suite.version,
            "fixed_utc": suite.fixed_utc,
            "timezone": suite.timezone,
            **current_fingerprints(ROOT, SUITE_PATH),
        },
        "pricing": GATE_A_PRICING,
        "executions": executions,
        "scores": summarize_scores(executions, THRESHOLDS),
        "totals": totals,
        "policy": GATE_A_POLICY,
    }


def passing_gate_a_bundle(revision: str) -> tuple[dict, dict, str, dict]:
    """Candidate, archived last-passing run, its byte digest, and approved comparison."""
    candidate = passing_gate_a_evidence(revision)
    baseline = passing_gate_a_evidence("b" * 40)
    baseline["run_id"] = "22222222-2222-4222-8222-222222222222"
    baseline["purpose"] = "baseline"
    baseline["declared_at"] = "2026-09-01T01:00:00+00:00"
    baseline["completed_at"] = "2026-09-01T01:15:00+00:00"
    baseline_bytes = json.dumps(baseline).encode()
    baseline_sha256 = hashlib.sha256(baseline_bytes).hexdigest()
    candidate_sha256 = hashlib.sha256(json.dumps(candidate).encode()).hexdigest()
    comparison = build_baseline_comparison(
        candidate,
        baseline,
        candidate_artifact_sha256=candidate_sha256,
        baseline_artifact_sha256=baseline_sha256,
    )
    comparison["human_review"] = {
        "status": "approved",
        "reviewer": "independent-reviewer",
        "reviewed_at": "2026-09-02T01:07:00Z",
        "baseline_confirmed_last_passing": True,
        "tone_reviewed": True,
        "reviewed_new_failure_pattern_ids": [
            pattern["id"] for pattern in comparison["failure_patterns"]["new"]
        ],
        "notes": "Reviewed tone, score deltas, and every new failure pattern.",
    }
    return candidate, baseline, baseline_sha256, comparison
