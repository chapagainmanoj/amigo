"""Throwaway synthetic-only flow preview; not an approved CBT exercise or personal-use mode."""

from dataclasses import dataclass, replace
from typing import Literal

Stage = Literal[
    "notice", "scenario", "fact", "interpretation", "takeaway", "done", "stopped", "exit"
]


@dataclass(frozen=True)
class Scenario:
    title: str
    event: str
    fact_choices: tuple[str, str]
    interpretation_choices: tuple[str, str]
    takeaway_choices: tuple[str, str]


SCENARIOS = (
    Scenario(
        title="Fictional meeting",
        event="Alex sent a meeting time suggestion this morning. By noon, no reply had arrived.",
        fact_choices=("No reply had arrived by noon.", "The colleague rejected Alex's suggestion."),
        interpretation_choices=(
            "The colleague may not have read it yet; the reason is unknown.",
            "The colleague definitely dislikes Alex's suggestion.",
        ),
        takeaway_choices=("The reply and reason remain unknown.", "No takeaway selected."),
    ),
    Scenario(
        title="Fictional recipe",
        event="Sam followed a new bread recipe. The loaf came out flatter than the recipe photo.",
        fact_choices=("This loaf was flatter than the photo.", "Sam can never bake good bread."),
        interpretation_choices=(
            "Several explanations are possible; this example does not establish a cause.",
            "This loaf proves Sam can never learn to bake.",
        ),
        takeaway_choices=(
            "One loaf does not establish a general conclusion.",
            "No takeaway selected.",
        ),
    ),
)


@dataclass(frozen=True)
class FlowState:
    stage: Stage = "notice"
    scenario_index: int | None = None
    fact_choice: int | None = None
    interpretation_choice: int | None = None
    takeaway_choice: int | None = None
    feedback: str = ""


async def transition(state: FlowState, action: str) -> FlowState:
    """Pure state transition: accepts menu keys only, never stores arbitrary input."""
    if action == "q":
        return FlowState(stage="exit")
    if action == "s":
        return FlowState(stage="stopped", feedback="Stopped. All in-memory selections cleared.")
    if action == "r" and state.stage in {"done", "stopped"}:
        return FlowState()
    if action == "b":
        if state.stage == "scenario":
            return FlowState()
        if state.stage == "fact":
            return FlowState(stage="scenario")
        if state.stage == "interpretation":
            return replace(state, stage="fact", fact_choice=None, feedback="")
        if state.stage == "takeaway":
            return replace(state, stage="interpretation", interpretation_choice=None, feedback="")
        if state.stage == "done":
            return replace(state, stage="takeaway", takeaway_choice=None, feedback="")
    if state.stage == "notice" and action == "c":
        return FlowState(stage="scenario")
    if state.stage == "scenario" and action in {"1", "2"}:
        return FlowState(stage="fact", scenario_index=int(action) - 1)
    if state.stage == "fact" and action in {"1", "2"}:
        if action == "2":
            return replace(state, feedback="That conclusion is not stated in this fictional event.")
        return replace(state, stage="interpretation", fact_choice=0, feedback="")
    if state.stage == "interpretation" and action in {"1", "2"}:
        if action == "2":
            return replace(state, feedback="The fictional event does not establish that certainty.")
        return replace(state, stage="takeaway", interpretation_choice=0, feedback="")
    if state.stage == "takeaway" and action in {"1", "2"}:
        return replace(state, stage="done", takeaway_choice=int(action) - 1, feedback="")
    return replace(state, feedback="Use a displayed menu key only. Personal text is not accepted.")
