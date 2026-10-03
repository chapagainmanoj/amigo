"""Every Mode Amigo knows about. Registering a Mode here is the whole integration."""

from src.agent.context import (
    active_reminder_ids,
    pending_task_ids,
    todays_tasks,
    yesterday_summary,
)
from src.agent.modes import ModeDefinition, TurnFacts
from src.agent.prompts import build_system_prompt
from src.agent.registry import ModeRegistry
from src.tools.toolsets import REMINDERS, TASKS


def daily_instructions(facts: TurnFacts) -> str:
    return build_system_prompt(facts.participant_name, current_time=facts.local_time)


DAILY = ModeDefinition(
    id="daily",
    name="Daily",
    purpose="Help me decide, remember, and follow through on what I intend to do today.",
    status="live",
    instructions=daily_instructions,
    toolsets=(TASKS, REMINDERS),
    tool_order=(
        "create_task",
        "update_task_status",
        "schedule_reminder",
        "apply_later",
        "move_task_planning_day",
        "cancel_reminders",
    ),
    context=(yesterday_summary, todays_tasks, pending_task_ids, active_reminder_ids),
    eval_suite="evals/gate_a/v1/cases.json",
    invalidating_inputs=("src/agent/prompts.py", "evals/gate_a/v1/cases.json"),
)

COACH = ModeDefinition(
    id="coach",
    name="Coach",
    purpose=(
        "Help me pursue one goal or habit I choose through a plan, check-ins, progress review, "
        "and adjustment."
    ),
    status="planned",
    handoffs=("daily",),
)

REFLECT = ModeDefinition(
    id="reflect",
    name="Reflect",
    purpose=(
        "Help me privately examine an experience, find my own takeaway, and optionally choose "
        "a next step."
    ),
    status="planned",
    handoffs=("daily",),
)

RECOMMENDER = ModeDefinition(
    id="recommender",
    name="Recommender",
    purpose=(
        "Help me choose among options in one approved domain using my stated preferences and "
        "explainable trade-offs."
    ),
    status="planned",
    handoffs=("daily",),
)


def build_registry() -> ModeRegistry:
    return ModeRegistry((DAILY, COACH, REFLECT, RECOMMENDER))
