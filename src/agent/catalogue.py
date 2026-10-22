"""Every Mode Amigo knows about. Registering a Mode here is the whole integration."""

from dataclasses import replace

from src.agent.coach import coach_instructions, coaching_context
from src.agent.context import (
    active_reminder_ids,
    pending_task_ids,
    todays_tasks,
    yesterday_summary,
)
from src.agent.modes import ModeDefinition, TurnFacts
from src.agent.prompts import build_system_prompt
from src.agent.recommender import recommender_context, recommender_instructions
from src.agent.reflect import REFLECT_CANDIDATE
from src.agent.registry import ModeRegistry
from src.mode_readiness import coach_entry_guard, reflect_entry_guard
from src.tools.coaching import COACHING
from src.tools.recommender import LAUNDRY
from src.tools.toolsets import REMINDERS, TASKS
from src.workflows import COACH_WORKFLOW_V1


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
    workflows=(COACH_WORKFLOW_V1,),
    name="Coach",
    purpose=(
        "Help me pursue one goal or habit I choose through a plan, check-ins, progress review, "
        "and adjustment."
    ),
    status="planned",
    instructions=coach_instructions,
    entry_guard=coach_entry_guard,
    toolsets=(COACHING,),
    context=(coaching_context,),
    entitlement="grant",
    eval_suite="evals/coach/v1/cases.json",
    invalidating_inputs=("src/agent/coach.py", "src/tools/coaching.py", "src/coaching.py"),
    handoffs=("daily",),
)

REFLECT = replace(REFLECT_CANDIDATE, entry_guard=reflect_entry_guard)

RECOMMENDER = ModeDefinition(
    id="recommender",
    name="Recommender",
    purpose=(
        "Help me choose among options in one approved domain using my stated preferences and "
        "explainable trade-offs."
    ),
    status="planned",
    instructions=recommender_instructions,
    toolsets=(LAUNDRY,),
    context=(recommender_context,),
    entitlement="grant",
    eval_suite="evals/recommender/v1/cases.json",
    invalidating_inputs=("src/agent/recommender.py", "src/tools/recommender.py"),
    handoffs=("daily",),
)


def build_registry() -> ModeRegistry:
    return ModeRegistry((DAILY, COACH, REFLECT, RECOMMENDER))
