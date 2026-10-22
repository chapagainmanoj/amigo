"""Fictional laundry comparisons never acquire real-world data or mutate participant state."""

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.agent.catalogue import DAILY
from src.agent.recommender import recommender_context, recommender_instructions
from src.agent.registry import ModeRegistry
from src.agent.runtime import ModeRuntime
from src.evaluation.gate_a import load_mode_suite
from src.tools.context import ToolContext
from src.tools.recommender import LAUNDRY, compare_laundry_options
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


class FixedClock:
    def utc_now(self):
        return datetime(2026, 10, 22, 12)

    def now_in_tz(self, timezone):
        return datetime(2026, 10, 22, 12)


@pytest.fixture
async def deps():
    store, channel = FakeStore(), FakeChannel()
    user = await store.create_user(123)
    session = await store.create_session(user["user_id"])
    return ToolContext(
        store=store,
        channel=channel,
        scheduler=FakeScheduler(),
        user=user,
        session_id=session["session_id"],
        chat_id=123,
        timezone="UTC",
        turn_id="laundry-test",
        clock=FixedClock(),
    )


@pytest.mark.parametrize(
    "args,recommendation",
    [
        (
            {
                "drying_options": ["outdoor", "dryer"],
                "dryer_suitable": True,
                "prefer_outdoor": True,
            },
            "dryer",
        ),
        ({"drying_options": ["outdoor", "indoor"]}, "postpone"),
        (
            {
                "drying_options": ["outdoor", "dryer"],
                "dryer_suitable": True,
                "require_outdoor": True,
            },
            "postpone",
        ),
    ],
)
async def test_rain_respects_suitability_soft_preference_and_hard_constraint(
    deps, args, recommendation
):
    result = await compare_laundry_options(
        SimpleNamespace(deps=deps),
        deadline="flexible",
        weather_fixture="rain",
        **args,
    )
    assert result["recommendation"] == recommendation
    assert result["weather"]["simulated"] is True
    assert "Simulated" in result["notice"] and result["effects"] == []
    assert deps.store.tasks == [] and deps.store.reminders == [] and deps.channel.sent == []


@pytest.mark.parametrize("fixture", ["unavailable", "stale", "wrong_interval"])
async def test_unusable_weather_abstains(deps, fixture):
    result = await compare_laundry_options(
        SimpleNamespace(deps=deps),
        ["outdoor"],
        "flexible",
        weather_fixture=fixture,
    )
    assert result["outcome"] == "abstain" and result["recommendation"] is None
    assert result["weather"]["fixture_id"] == fixture
    assert "source" in result["weather"]


async def test_flexible_postpones_before_indoor_but_urgent_can_consider_it(deps):
    ctx = SimpleNamespace(deps=deps)
    flexible = await compare_laundry_options(
        ctx, ["outdoor", "indoor"], "flexible", weather_fixture="rain"
    )
    urgent = await compare_laundry_options(
        ctx, ["outdoor", "indoor"], "urgent", weather_fixture="rain", available_minutes=120
    )
    assert flexible["recommendation"] == "postpone"
    assert urgent["recommendation"] == "indoor" and "unverified" in urgent["reason"]


@pytest.mark.parametrize("options", [["indoor"], ["dryer"]])
async def test_non_weather_options_do_not_collect_weather_or_location(deps, options):
    result = await compare_laundry_options(
        SimpleNamespace(deps=deps),
        options,
        "flexible",
        dryer_suitable=True,
    )
    assert result["weather"] is None and result["outcome"] == "recommend"


@pytest.mark.parametrize(
    "options,deadline,suitable",
    [
        ([], "flexible", None),
        (["outdoor"], "unknown", None),
        (["dryer"], "flexible", None),
        (["outdoor"], "urgent", None),
    ],
)
async def test_missing_facts_ask_one_question(deps, options, deadline, suitable):
    result = await compare_laundry_options(
        SimpleNamespace(deps=deps),
        options,
        deadline,
        dryer_suitable=suitable,
    )
    assert result["outcome"] == "clarify" and result["reason"].count("?") == 1


async def test_unsuitable_dryer_is_never_recommended(deps):
    result = await compare_laundry_options(
        SimpleNamespace(deps=deps),
        ["dryer"],
        "flexible",
        dryer_suitable=False,
    )
    assert result["outcome"] == "abstain"


async def test_unselected_simulated_weather_is_not_silently_invented(deps):
    result = await compare_laundry_options(SimpleNamespace(deps=deps), ["outdoor"], "flexible")
    assert result["outcome"] == "clarify" and result["weather"] is None


async def test_runtime_offers_only_comparison_and_no_daily_context(deps):
    mode = replace(
        DAILY,
        id="recommender",
        name="Recommender",
        toolsets=(LAUNDRY,),
        tool_order=(),
        instructions=recommender_instructions,
        context=(recommender_context,),
        eval_suite="evals/recommender/v1/cases.json",
        invalidating_inputs=(),
    )
    runtime = ModeRuntime(ModeRegistry([mode]))
    steps = []

    def model(messages, info):
        assert {tool.name for tool in info.function_tools} == {"compare_laundry_options"}
        steps.append(True)
        if len(steps) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "compare_laundry_options",
                        {
                            "drying_options": ["indoor"],
                            "deadline": "flexible",
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("Indoor drying is available; timing is uncertain.")])

    result = await runtime.run_turn(
        deps,
        "Only indoor drying, flexible deadline.",
        requested_mode="recommender",
        model=FunctionModel(model),
    )
    assert "Indoor" in result.output
    assert deps.store.tasks == [] and deps.store.reminders == []
    section = await recommender_context(deps)
    assert deps.user["user_id"] not in section and "no network" in section


def test_suite_and_scripted_subset_are_complete():
    root = Path(__file__).resolve().parents[1]
    suite = load_mode_suite(root / "evals/recommender/v1/cases.json", "recommender")
    subset = json.loads((root / "evals/recommender/v1/deterministic.json").read_text())
    assert len(suite.cases) == 16
    assert {case.id for case in suite.cases} == {case["case_id"] for case in subset["cases"]}
    assert all(case.turns[0].expected_state.unchanged for case in suite.cases)


async def test_complete_scripted_eval_runs_through_owned_orchestrator(monkeypatch):
    from scripts import run_mode_deterministic_eval
    from src.turns import SessionTurnOrchestrator

    mode = replace(
        DAILY,
        id="recommender",
        name="Recommender",
        toolsets=(LAUNDRY,),
        tool_order=(),
        instructions=recommender_instructions,
        context=(recommender_context,),
        eval_suite="evals/recommender/v1/cases.json",
        invalidating_inputs=(),
    )
    runtime = ModeRuntime(ModeRegistry([mode]))
    monkeypatch.setattr(
        run_mode_deterministic_eval,
        "default_turn_orchestrator",
        SessionTurnOrchestrator(runtime),
    )
    assert await run_mode_deterministic_eval.evaluate_mode(mode) == []
