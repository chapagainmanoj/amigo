"""Focused engineering checks; not validation of a CBT method or personal-input safety."""

from dataclasses import replace

import pytest
from research_engine import MAX_QUESTIONS, ResearchEngine, ScriptedProvider


@pytest.mark.parametrize("fixture_id", ["meeting", "recipe"])
@pytest.mark.parametrize("strategy", ["fixed", "adaptive"])
async def test_run_is_finite_with_one_question_and_optional_takeaway(fixture_id, strategy):
    engine = ResearchEngine()
    state = await engine.start(fixture_id, strategy)
    while state.status == "asking":
        assert state.question_id is not None
        assert (await engine.question(state)).count("?") == 1
        assert await engine.scripted_answer(state)
        action = "skip" if state.question_id == "takeaway" else "answer"
        state = await engine.advance(state, action)
    assert state.status == "complete"
    assert state.selections == len(state.asked) == MAX_QUESTIONS
    assert "takeaway" in state.skipped
    assert "takeaway" not in state.answered
    assert await engine.question(state) is None
    assert await engine.advance(state, "answer") == state


@pytest.mark.parametrize(
    "fixture_id,branch", [("meeting", "uncertainty"), ("recipe", "clarify_fact")]
)
async def test_fixed_and_adaptive_branches_differ(fixture_id, branch):
    traces = {}
    for strategy in ("fixed", "adaptive"):
        engine = ResearchEngine()
        state = await engine.start(fixture_id, strategy)
        while state.status == "asking":
            state = await engine.advance(state, "answer")
        traces[strategy] = state.asked
    assert "alternative" in traces["fixed"]
    assert branch in traces["adaptive"]
    assert traces["fixed"] != traces["adaptive"]


@pytest.mark.parametrize("skip_id", ["fact", "thought"])
async def test_skipped_answers_do_not_authorize_adaptive_branch(skip_id):
    engine = ResearchEngine()
    state = await engine.start("meeting", "adaptive")
    while state.status == "asking":
        state = await engine.advance(state, "skip" if state.question_id == skip_id else "answer")
    assert "uncertainty" not in state.asked
    assert "alternative" in state.asked


@pytest.mark.parametrize("step", range(MAX_QUESTIONS))
async def test_stop_clears_all_run_selections_at_every_step(step):
    engine = ResearchEngine()
    state = await engine.start("recipe", "adaptive")
    for _ in range(step):
        state = await engine.advance(state, "answer")
    state = await engine.advance(state, "stop")
    assert state.status == "stopped"
    assert state.fixture_id is state.question_id is None
    assert state.asked == state.answered == state.skipped == ()
    assert state.selections == 0
    assert await engine.advance(state, "answer") == state


async def test_unknown_fixture_strategy_and_arbitrary_input_refused_without_storage():
    engine = ResearchEngine()
    assert (await engine.start("personal input sentinel")).status == "failed"
    assert (await engine.start("meeting", "unknown")).status == "failed"
    state = await engine.start("meeting")
    assert await engine.advance(state, "personal input sentinel") == state
    assert "sentinel" not in repr(state)


class BrokenProvider(ScriptedProvider):
    async def choose(self, state):
        raise RuntimeError("private-error-sentinel")


class UndeclaredProvider(ScriptedProvider):
    async def choose(self, state):
        return "diagnose"


@pytest.mark.parametrize("provider", [BrokenProvider(), UndeclaredProvider()])
async def test_provider_failure_and_unlisted_pattern_fail_closed_without_error_content(provider):
    engine = ResearchEngine(provider)
    state = await engine.start("meeting")
    assert state.status == "failed"
    assert state.question_id is None
    assert state.selections == 1
    assert "private-error-sentinel" not in repr(state)
    assert await engine.advance(state, "answer") == state


async def test_selection_budget_prevents_further_provider_dispatch():
    engine = ResearchEngine(BrokenProvider())
    state = replace(await ResearchEngine().start("meeting"), selections=MAX_QUESTIONS)
    state = await engine.advance(state, "skip")
    assert state.status == "complete"
    assert state.selections == MAX_QUESTIONS
    assert state.error is None


async def test_every_question_can_be_skipped_without_any_answers():
    engine = ResearchEngine()
    state = await engine.start("recipe", "adaptive")
    while state.status == "asking":
        state = await engine.advance(state, "skip")
    assert state.status == "complete"
    assert state.answered == ()
    assert len(state.skipped) == MAX_QUESTIONS


class RepeatingProvider(ScriptedProvider):
    async def choose(self, state):
        return "fact"


async def test_repeated_pattern_fails_closed_instead_of_looping():
    engine = ResearchEngine(RepeatingProvider())
    state = await engine.start("meeting")
    state = await engine.advance(state, "answer")
    assert state.status == "failed"
    assert state.error == "question_not_permitted"
    assert state.selections == 2
