"""Fictional candidate evaluation cannot enable real participant processing."""

from dataclasses import replace
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from scripts import run_mode_deterministic_eval
from scripts.run_gate_a_eval import _evaluation_registry, _run_execution
from src.agent.catalogue import build_registry
from src.evaluation.gate_a import load_mode_suite, tool_schema

# Candidate evaluation never changes the application catalogue.
CATALOGUE_STATUS = {"coach": "live", "reflect": "live", "recommender": "live"}


@pytest.mark.parametrize("mode_id", ["coach", "reflect", "recommender"])
async def test_declared_candidate_scripted_suite_passes(mode_id):
    mode = _evaluation_registry(mode_id, True)[mode_id]
    assert await run_mode_deterministic_eval.evaluate_mode(mode, candidate=True) == []
    assert build_registry()[mode_id].status == CATALOGUE_STATUS[mode_id]


def test_daily_cannot_use_candidate_bypass():
    with pytest.raises(ValueError, match="Daily cannot bypass"):
        _evaluation_registry("daily", True)


@pytest.mark.parametrize("mode_id", ["coach", "reflect", "recommender"])
def test_specialized_tools_never_include_daily_writes(mode_id):
    names = {item["name"] for item in tool_schema(mode_id)}
    assert not names & {
        "create_task",
        "schedule_reminder",
        "update_task_status",
        "cancel_reminders",
    }
    assert "propose_handoff" in names


async def test_candidate_runner_seeds_only_isolated_synthetic_grant():
    mode_id = "coach"
    suite = load_mode_suite(Path("evals/coach/v1/cases.json"), mode_id)
    result = await _run_execution(
        suite.cases[0],
        suite,
        1,
        FunctionModel(
            lambda messages, info: ModelResponse(parts=[TextPart("Which goal or habit?")])
        ),
        mode_id,
        candidate=True,
    )
    assert result["passed"]
    assert result["turns"][0]["state"]["tasks"] == []
    assert build_registry()[mode_id].entry_guard is not None


def test_candidate_cannot_mutate_application_definition():
    original = build_registry()["reflect"]
    candidate = _evaluation_registry("reflect", True)["reflect"]
    assert candidate.status == "live" and candidate.entry_guard is None
    assert original.entry_guard is not None
    assert replace(candidate, entry_guard=original.entry_guard) == original


def test_punctuation_prohibition_matches_literal_not_empty_normalization():
    from src.evaluation.gate_a import ResponseProperties, _response_checks

    expected = ResponseProperties(must_not_include=["?"])
    assert _response_checks("Stopped.", expected) == (True, [])
    assert _response_checks("Stopped?", expected)[0] is False
    required = ResponseProperties(must_include_all=["?"])
    assert _response_checks("Which goal?", required)[0] is True
    assert _response_checks("Choose a goal.", required)[0] is False


def test_model_evidence_currency_binds_admission_guard():
    from src.evaluation.model_policy import fallback_currency

    root = Path(__file__).resolve().parents[1]
    original = build_registry()["reflect"]
    candidate = _evaluation_registry("reflect", True)["reflect"]
    assert fallback_currency(original, root)["entry_guard"] is not None
    assert fallback_currency(candidate, root)["entry_guard"] is None


@pytest.mark.parametrize("country", ["éé", "１２", "USA", "U1"])
async def test_local_consent_country_matches_sql_ascii_contract(country):
    from src.memory.proactive import LocalProactiveState

    state = LocalProactiveState()
    with pytest.raises(ValueError):
        await state.set_consent("owner", "reflect-v1", "fictional-policy", country_code=country)
    assert state.consents == {}
