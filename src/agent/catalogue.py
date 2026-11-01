"""Every Mode Amigo knows about. Registering a Mode here is the whole integration."""

from dataclasses import replace

from src.access import FULL_ACCESS
from src.agent.cbt import CBT as CBT_CANDIDATE
from src.agent.coach import coach_instructions, coaching_context
from src.agent.context import (
    active_reminder_ids,
    pending_task_ids,
    todays_tasks,
    yesterday_summary,
)
from src.agent.modes import DAILY_MODE_ID, ModeDefinition, ModelPolicy, TurnFacts
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
    id=DAILY_MODE_ID,
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
    examples=(
        "Add 'call the bank' to today",
        "Remind me to stretch at 6pm",
        "What's left on my plan?",
    ),
)

COACH = ModeDefinition(
    id="coach",
    workflows=(COACH_WORKFLOW_V1,),
    name="Coach",
    purpose=(
        "Help me pursue one goal or habit I choose through a plan, check-ins, progress review, "
        "and adjustment."
    ),
    status="live",
    instructions=coach_instructions,
    # Evaluated on this model (coach-gemini-3.8-flash.json); Daily keeps the configured default.
    model=ModelPolicy(primary="google:gemini-3.8-flash"),
    entry_guard=coach_entry_guard,
    toolsets=(COACHING,),
    context=(coaching_context,),
    eval_suite="evals/coach/v1/cases.json",
    invalidating_inputs=("src/agent/coach.py", "src/tools/coaching.py", "src/coaching.py"),
    handoffs=(DAILY_MODE_ID,),
    examples=(
        "Walk 20 minutes, 3 days a week",
        "Read 10 pages every weekday evening",
        "Have 4 alcohol-free days each week",
    ),
)

# Reflect and Recommender run on the model their suites were evaluated on (56/60 and 43/48, not
# passing). They are live for full-access accounts only, on the owner's call (23 Oct 2026).
REFLECT = replace(
    REFLECT_CANDIDATE,
    status="live",
    model=ModelPolicy(primary="google:gemini-3.8-flash"),
    entry_guard=reflect_entry_guard,
    entitlement=FULL_ACCESS,
    examples=(
        "Debrief a meeting that didn't go well",
        "Help me think through a decision I'm stuck on",
        "Do a quick weekly review",
    ),
)

RECOMMENDER = ModeDefinition(
    id="recommender",
    name="Recommender",
    purpose=(
        "Help me choose among options in one approved domain using my stated preferences and "
        "explainable trade-offs."
    ),
    status="live",
    model=ModelPolicy(primary="google:gemini-3.8-flash"),
    instructions=recommender_instructions,
    toolsets=(LAUNDRY,),
    context=(recommender_context,),
    entitlement=FULL_ACCESS,
    eval_suite="evals/recommender/v1/cases.json",
    invalidating_inputs=("src/agent/recommender.py", "src/tools/recommender.py"),
    handoffs=(DAILY_MODE_ID,),
    examples=(
        "Which detergent for sensitive skin?",
        "Cold or warm wash for dark jeans?",
    ),
)


# CBT research takes the participant's own thoughts: live for full-access accounts only, on the
# owner's call (30 Oct 2026). No evaluated evidence yet; Reflect's guard and crisis routing apply.
CBT = replace(
    CBT_CANDIDATE,
    status="live",
    model=ModelPolicy(primary="google:gemini-3.8-flash"),
    entry_guard=reflect_entry_guard,
    entitlement=FULL_ACCESS,
)


def build_registry() -> ModeRegistry:
    return ModeRegistry((DAILY, COACH, REFLECT, RECOMMENDER, CBT))
