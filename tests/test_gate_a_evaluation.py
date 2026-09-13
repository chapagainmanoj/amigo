"""Deterministic Gate A suite and scorer contract tests."""

import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.evaluation.gate_a import (
    CATEGORY_COUNTS,
    THRESHOLDS,
    ExpectedState,
    GateASuite,
    ResponseProperties,
    load_suite,
    score_turn,
)

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


def _suite_payload():
    return json.loads(SUITE_PATH.read_text())


def test_contract_rejects_a_suite_that_drops_a_required_behaviour_family():
    """Composition counts cannot prove criterion 1 coverage; the tag families must."""
    payload = _suite_payload()
    for case in payload["cases"]:
        case["tags"] = [tag for tag in case["tags"] if tag != "greeting"] or ["single"]

    with pytest.raises(ValidationError) as error:
        GateASuite.model_validate(payload)

    assert "greeting" in str(error.value)


def test_contract_rejects_a_turn_that_declares_no_prohibited_tools():
    """Criterion 2 requires a declared prohibition, not an omitted one."""
    payload = _suite_payload()
    payload["cases"][0]["turns"][0]["prohibited_tools"] = []

    with pytest.raises(ValidationError):
        GateASuite.model_validate(payload)


def test_every_approved_turn_declares_the_full_criterion_two_contract():
    suite = load_suite(SUITE_PATH)

    for case in suite.cases:
        for turn in case.turns:
            assert turn.prohibited_tools, f"{case.id} omits prohibited Tools"
            assert turn.clarification in {"required", "not_required"}
            assert turn.response is not None
            assert turn.expected_state is not None


def test_contract_rejects_a_turn_that_asserts_nothing():
    """Every response and state field defaults to "do not care", so silence is a free pass."""
    payload = _suite_payload()
    payload["cases"][0]["turns"][0] = {
        "message": "Add buy oat milk to my list.",
        "prohibited_tools": ["cancel_reminders"],
        "clarification": "not_required",
        "response": {},
        "expected_state": {},
    }

    with pytest.raises(ValidationError) as error:
        GateASuite.model_validate(payload)

    assert "expected Tools" in str(error.value)


def test_contract_rejects_a_turn_whose_expected_state_declares_nothing():
    payload = _suite_payload()
    payload["cases"][0]["turns"][0]["expected_state"] = {}

    with pytest.raises(ValidationError) as error:
        GateASuite.model_validate(payload)

    assert "expected resulting state" in str(error.value)


def test_a_turn_that_asserts_nothing_would_otherwise_score_as_a_pass():
    """Why the contract above matters: an empty assertion set passes every metric."""
    from src.evaluation.gate_a import EvalTurn

    turn = EvalTurn.model_construct(
        message="Add buy oat milk to my list.",
        expected_tools={},
        prohibited_tools=["cancel_reminders"],
        clarification="not_required",
        response=ResponseProperties(),
        expected_state=ExpectedState(),
    )

    score = score_turn(
        turn,
        trace=[],
        response="Okay.",
        state={"tasks": [], "pending_reminders": [], "aliases": {}, "state_hash": "H"},
        before_state_hash="H",
    )

    assert score["passed"], "the model created nothing and still passed — hence the contract"
