"""Supplementary scorer regressions; the approved sixty-case inventory stays unchanged."""

import json
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from scripts.run_gate_a_eval import _setup_case, _state
from src.evaluation.gate_a import EvalCase, extract_trace, load_suite, score_turn
from src.turns import default_turn_orchestrator

ROOT = Path(__file__).parents[1]
DATA = json.loads((ROOT / "evals/gate_a/v1/budget-regressions.json").read_text())


@pytest.mark.parametrize("index", range(len(DATA["cases"])))
async def test_zero_proactive_budget_preserves_daily_request(index):
    suite = load_suite(ROOT / "evals/gate_a/v1/cases.json")
    case = EvalCase.model_validate(DATA["cases"][index])
    store, context, aliases = await _setup_case(case, suite, 1)
    assert context.user["daily_message_budget"] == 0
    responses = list(DATA["deterministic"][index]["responses"])

    def scripted(messages, info):
        response = responses.pop(0)
        if "text" in response:
            return ModelResponse(parts=[TextPart(response["text"])])
        args = {
            key: aliases[value[6:]]
            if isinstance(value, str) and value.startswith("$task:")
            else value
            for key, value in response["args"].items()
        }
        return ModelResponse(parts=[ToolCallPart(response["tool"], args)])

    for turn in case.turns:
        before = _state(store, aliases)
        result = await default_turn_orchestrator.run_turn(
            context, turn.message, requested_mode="daily", model=FunctionModel(scripted)
        )
        trace, response = extract_trace(result.messages)
        score = score_turn(
            turn,
            trace=trace,
            response=response,
            state=_state(store, aliases),
            before_state_hash=before["state_hash"],
        )
        assert score["passed"], score
    assert not responses
    assert store._proactive_state.reservations == {}
