"""Deterministic Gate A suite and scorer contract tests."""

from collections import Counter
from pathlib import Path

from src.evaluation.gate_a import CATEGORY_COUNTS, THRESHOLDS, load_suite, score_turn

SUITE_PATH = Path(__file__).parents[1] / "evals/gate_a/v1/cases.json"


def test_gate_a_suite_has_exact_approved_inventory_and_metric_coverage():
    suite = load_suite(SUITE_PATH)

    assert len(suite.cases) == 60
    assert Counter(case.category for case in suite.cases) == CATEGORY_COUNTS
    assert {metric for case in suite.cases for metric in case.metrics} == set(THRESHOLDS)
    assert all(case.setup is not None for case in suite.cases)
    assert all(case.turns for case in suite.cases)
    assert all(turn.response for case in suite.cases for turn in case.turns)
    assert all(turn.expected_state for case in suite.cases for turn in case.turns)


def test_scorer_rejects_prohibited_mutation_and_changed_state():
    suite = load_suite(SUITE_PATH)
    turn = next(case for case in suite.cases if case.id == "ga-hard-03").turns[0]
    state = {
        "tasks": [{"title": "hidden task"}],
        "pending_reminders": [],
        "aliases": {},
        "state_hash": "changed",
    }

    score = score_turn(
        turn,
        trace=[{"kind": "tool_call", "tool": "create_task", "args": {}}],
        response="Done silently.",
        state=state,
        before_state_hash="before",
    )

    assert not score["passed"]
    assert not score["tool_state_passed"]
    assert not score["no_unnecessary_mutation_passed"]


def test_scorer_accepts_clarification_without_state_change():
    suite = load_suite(SUITE_PATH)
    turn = next(case for case in suite.cases if case.id == "ga-task-06").turns[0]
    state = {
        "tasks": [],
        "pending_reminders": [],
        "aliases": {},
        "state_hash": "same",
    }

    score = score_turn(
        turn,
        trace=[{"kind": "tool_call", "tool": "create_task", "args": {}}],
        response="Do you mean 7 AM or 7 PM, and on which date?",
        state=state,
        before_state_hash="same",
    )

    assert score["passed"]
    assert score["clarification_passed"]

