"""Synthetic-only research MVP: provisional questions, not a reviewed CBT protocol."""

from dataclasses import dataclass, replace
from typing import Literal

VERSION = "synthetic-question-engine-v1"
MAX_QUESTIONS = 4  # Provisional engineering choice, not approved personal protocol.
Strategy = Literal["fixed", "adaptive"]

QUESTIONS = {
    "fact": "What events are described in this fictional situation?",
    "clarify_fact": "Which detail is missing from the fictional account?",
    "thought": "What interpretation does the fictional person report?",
    "uncertainty": "What remains unknown in this fictional account?",
    "alternative": "What other explanation could fit without claiming it is correct?",
    "takeaway": "Would the fictional person choose a takeaway, or choose none?",
}


@dataclass(frozen=True)
class Fixture:
    event: str
    responses: tuple[tuple[str, str], ...]
    branch: Literal["clarify_fact", "uncertainty", "alternative"]


FIXTURES = {
    "meeting": Fixture(
        "Alex sent a meeting suggestion this morning. There was no reply by noon.",
        (
            ("fact", "A suggestion was sent; no reply had arrived by noon."),
            ("thought", "Alex wonders whether the suggestion was unwelcome."),
            ("uncertainty", "The recipient's reason and whether they read it remain unknown."),
            ("alternative", "They might not have read it; this is a possibility, not a fact."),
            ("takeaway", "Alex chooses no takeaway."),
        ),
        "uncertainty",
    ),
    "recipe": Fixture(
        "Sam says a new bread recipe went differently than expected; details are missing.",
        (
            ("fact", "Sam describes a different result but has not described its appearance."),
            ("clarify_fact", "The account does not say how the loaf differed."),
            ("thought", "Sam wonders whether one attempt means learning will be difficult."),
            ("alternative", "One attempt need not establish a general result."),
            ("takeaway", "Sam chooses to leave the conclusion open."),
        ),
        "clarify_fact",
    ),
}


@dataclass(frozen=True)
class RunState:
    status: Literal["idle", "asking", "complete", "stopped", "failed"] = "idle"
    fixture_id: str | None = None
    strategy: Strategy = "fixed"
    question_id: str | None = None
    asked: tuple[str, ...] = ()
    answered: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    selections: int = 0
    error: str | None = None


@dataclass
class ScriptedProvider:
    """Select only versioned question IDs; no generated wording or external services."""

    async def choose(self, state: RunState) -> str:
        if state.strategy == "fixed":
            sequence = ("fact", "thought", "alternative", "takeaway")
        else:
            branch = FIXTURES[state.fixture_id].branch
            # Adapt only when the preceding fictional answer was actually consumed.
            if "fact" not in state.answered:
                branch = "alternative"
            if branch == "clarify_fact":
                sequence = ("fact", "clarify_fact", "thought", "takeaway")
            else:
                if "thought" not in state.answered:
                    branch = "alternative"
                sequence = ("fact", "thought", branch, "takeaway")
        return sequence[len(state.asked)]


class ResearchEngine:
    """One explicit synthetic fixture per run, with hard selection and question budgets."""

    def __init__(self, provider: ScriptedProvider | None = None):
        self.provider = provider or ScriptedProvider()

    async def start(self, fixture_id: str, strategy: Strategy = "fixed") -> RunState:
        if fixture_id not in FIXTURES or strategy not in {"fixed", "adaptive"}:
            return RunState(status="failed", error="synthetic_fixture_or_strategy_required")
        return await self._next(RunState(fixture_id=fixture_id, strategy=strategy))

    async def advance(self, state: RunState, action: str) -> RunState:
        if action == "stop":
            return RunState(status="stopped")
        if state.status != "asking":
            return state
        if action not in {"answer", "skip"}:
            return state  # Never retain or echo unrecognized/personal text.
        if action == "answer":
            state = replace(state, answered=(*state.answered, state.question_id))
        else:
            state = replace(state, skipped=(*state.skipped, state.question_id))
        return await self._next(state)

    async def _next(self, state: RunState) -> RunState:
        if len(state.asked) >= MAX_QUESTIONS or state.selections >= MAX_QUESTIONS:
            return replace(state, status="complete", question_id=None)
        state = replace(state, selections=state.selections + 1)
        try:
            question_id = await self.provider.choose(state)
        except Exception:
            return replace(state, status="failed", question_id=None, error="provider_failed")
        if question_id not in QUESTIONS or question_id in state.asked:
            return replace(state, status="failed", question_id=None, error="question_not_permitted")
        return replace(state, status="asking", question_id=question_id,
                       asked=(*state.asked, question_id))

    async def question(self, state: RunState) -> str | None:
        return QUESTIONS.get(state.question_id) if state.status == "asking" else None

    async def scripted_answer(self, state: RunState) -> str | None:
        if state.status != "asking" or state.fixture_id not in FIXTURES:
            return None
        return dict(FIXTURES[state.fixture_id].responses).get(state.question_id)
