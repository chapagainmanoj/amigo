"""Pydantic AI agent — single tool-calling loop replaces classify→extract→resolve pipeline.

The agent sees the user message, decides which tools to call, observes results,
and produces a final reply — all in one turn. Side effects execute through injected
services (store, scheduler), keeping testability via fakes.

See ADR 0002 for rationale.
"""

import hashlib
import logging
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from src.agent.prompts import build_system_prompt
from src.channels.base import MessageChannel
from src.commands.base import CommandContext
from src.memory.context import ContextBuilder
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler
from src.time_resolution import TimeResolution, resolve_reminder_time
from src.tools.reminders import CancelRemindersTool, ScheduleReminderTool
from src.tools.tasks import CreateTaskTool, UpdateTaskStatusTool
from src.utils import now_in_tz

logger = logging.getLogger(__name__)


@dataclass
class AgentDeps:
    """Per-request dependencies injected into every tool call."""

    store: MemoryStore
    scheduler: ReminderScheduler
    channel: MessageChannel
    user: dict
    session_id: str
    chat_id: int
    timezone: str
    turn_id: str


def _get_model_name() -> str:
    """Resolve model name from settings, lazy to avoid import-time settings access."""
    from src.config import settings
    model = settings.default_model
    # Pydantic AI uses provider-prefixed names for Google models
    if model.startswith("gemini-"):
        return f"google:{model}"
    return model


# ── Agent definition ──
# Constructed once at module level. Per-request state goes through AgentDeps.
# model=None so importing this module never triggers settings/API key resolution.
# The model is provided at run() time via _get_model_name().
amigo_agent = Agent(
    deps_type=AgentDeps,
    output_type=str,
    retries=1,
)


@amigo_agent.system_prompt
async def _build_system_prompt(ctx: RunContext[AgentDeps]) -> str:
    """Dynamic system prompt with user context, tasks, and time."""
    deps = ctx.deps
    user = deps.user
    name = user.get("name") or "friend"
    tz = user.get("timezone") or "UTC"
    local_time = now_in_tz(tz).strftime("%Y-%m-%d %H:%M %A")

    base_prompt = build_system_prompt(name, current_time=local_time)

    # Build task context
    context_builder = ContextBuilder(deps.store)
    tasks_block = await context_builder._build_tasks_block(user["user_id"], tz)
    yesterday_summary = await context_builder._get_yesterday_summary(user["user_id"], tz)

    # Pending tasks with IDs for status update tool
    pending = await deps.store.get_today_tasks(user["user_id"], tz)
    pending_tasks = [task for task in pending if task["status"] == "pending"]

    sections = [base_prompt]

    if yesterday_summary:
        sections.append(f"\n<yesterday_summary>\n{yesterday_summary}\n</yesterday_summary>")

    if tasks_block:
        sections.append(f"\n<todays_tasks>\n{tasks_block}\n</todays_tasks>")

    if pending_tasks:
        task_lines = "\n".join(
            f"- task_id={t['task_id']}: {t['title']} (status: {t['status']})"
            for t in pending_tasks
        )
        sections.append(
            f"\n<pending_task_ids>\n"
            f"Use these task_id values when calling update_task_status:\n"
            f"{task_lines}\n"
            f"</pending_task_ids>"
        )

    return "\n".join(sections)


# ── Tools ──


@amigo_agent.tool
async def create_task(
    ctx: RunContext[AgentDeps],
    title: str,
    category: str = "other",
    reminder_time: str | None = None,
    confirmed_reminder_time: str | None = None,
) -> str:
    """Create a new task for the user.

    When reminder_time is provided the reminder is scheduled automatically
    as part of this call — no separate schedule_reminder call is needed.

    Args:
        title: Clear, actionable task title.
        category: One of: health, work, personal, social, other.
        reminder_time: Optional natural language time like "3pm", "in 10 minutes",
            "after lunch". Pass this to create the task and set the reminder in one step.
        confirmed_reminder_time: The exact confirmation label returned by a previous tool
            result, supplied only after the user explicitly confirms it.
    """
    deps = ctx.deps
    resolution = None
    if reminder_time:
        resolution = _resolve_time(deps, reminder_time)
        blocked = _resolution_block_message(resolution, confirmed_reminder_time)
        if blocked:
            return blocked

    tool = CreateTaskTool(deps.store)
    input_fingerprint = hashlib.sha256(
        f"{title.strip()}\0{category}\0{deps.session_id}".encode()
    ).hexdigest()[:16]
    result = await tool.run(
        context=CommandContext(
            actor_user_id=deps.user["user_id"],
            surface="telegram",
            idempotency_key=f"telegram:{deps.turn_id}:create-task:{input_fingerprint}",
        ),
        title=title,
        category=category,
        session_id=deps.session_id,
    )
    task = result["task"]

    # Schedule reminder if time was provided
    if resolution:
        reminder_result = await _schedule_resolved_reminder(deps, task, resolution)
        return f"Created task '{title}' with reminder for {reminder_result}."

    return f"Created task '{title}'."


@amigo_agent.tool
async def update_task_status(
    ctx: RunContext[AgentDeps],
    task_id: str,
    status: str,
) -> str:
    """Update a task's status when the user indicates completion, skipping, or deferral.

    Args:
        task_id: The task_id from the pending tasks list in context.
        status: One of: "completed", "skipped", "cancelled".
    """
    deps = ctx.deps
    tool = UpdateTaskStatusTool(deps.store)
    result = await tool.run(
        context=CommandContext(
            actor_user_id=deps.user["user_id"],
            surface="telegram",
            idempotency_key=f"telegram:{deps.turn_id}:resolve-task:{task_id}:{status}",
        ),
        task_id=task_id,
        status=status,
    )
    task_title = result["task"].get("title", "task")
    return f"Updated '{task_title}' to {status}."


@amigo_agent.tool
async def schedule_reminder(
    ctx: RunContext[AgentDeps],
    task_id: str,
    time_expression: str,
    confirmed_time: str | None = None,
) -> str:
    """Schedule or reschedule a reminder for an already-created task.

    Use this to add or change a reminder on an existing task. When creating a
    new task with a reminder, pass reminder_time to create_task instead.

    Args:
        task_id: The task_id to schedule a reminder for.
        time_expression: Natural language time like "3pm", "in 30 minutes", "after lunch".
        confirmed_time: The exact confirmation label returned by a previous tool result,
            supplied only after the user explicitly confirms it.
    """
    deps = ctx.deps
    task = None
    today_tasks = await deps.store.get_today_tasks(deps.user["user_id"], deps.timezone)
    inbox_tasks = await deps.store.get_inbox_tasks(deps.user["user_id"])
    for t in [*today_tasks, *inbox_tasks]:
        if t["task_id"] == task_id:
            task = t
            break

    if not task:
        return f"Task {task_id} not found."

    resolution = _resolve_time(deps, time_expression)
    blocked = _resolution_block_message(resolution, confirmed_time)
    if blocked:
        return blocked
    exact = await _schedule_resolved_reminder(deps, task, resolution)
    return f"Reminder scheduled for '{task['title']}' on {exact}."


@amigo_agent.tool
async def cancel_reminders(
    ctx: RunContext[AgentDeps],
    task_id: str,
) -> str:
    """Cancel all pending reminders for a task.

    Args:
        task_id: The task_id to cancel reminders for.
    """
    deps = ctx.deps
    tool = CancelRemindersTool(deps.store, deps.scheduler)
    result = await tool.run(task_id=task_id, user_id=deps.user["user_id"])
    count = len(result["reminder_ids"])
    return f"Cancelled {count} reminder(s)."


# ── Time resolution helper ──


def parse_time_expression(time_expr: str, timezone: str) -> TimeResolution:
    """Compatibility entry point returning the full typed time interpretation."""
    return resolve_reminder_time(time_expr, timezone)


def _resolve_time(deps: AgentDeps, expression: str) -> TimeResolution:
    return resolve_reminder_time(
        expression,
        deps.timezone,
        wake_time=deps.user.get("wake_time", "07:30"),
        sleep_time=deps.user.get("sleep_time", "23:00"),
    )


def _resolution_block_message(
    resolution: TimeResolution,
    confirmed_interpretation: str | None,
) -> str | None:
    if resolution.clarification_required:
        return f"I need clarification before saving a reminder: {resolution.reason}"
    if (
        resolution.confirmation_required
        and confirmed_interpretation != resolution.exact_label
    ):
        detail = f" {resolution.reason}" if resolution.reason else ""
        return (
            f"Please confirm the reminder for {resolution.exact_label}.{detail} "
            "Nothing has been scheduled yet."
        )
    return None


async def _schedule_resolved_reminder(
    deps: AgentDeps,
    task: dict,
    resolution: TimeResolution,
) -> str:
    if resolution.utc_instant is None or resolution.exact_label is None:
        raise ValueError("Reminder time is not resolved")
    tool = ScheduleReminderTool(deps.store, deps.scheduler)
    input_fingerprint = hashlib.sha256(
        (
            f"{task['task_id']}\0{resolution.utc_instant.isoformat()}\0"
            f"{resolution.timezone}"
        ).encode()
    ).hexdigest()[:16]
    await tool.run_exact(
        context=CommandContext(
            actor_user_id=deps.user["user_id"],
            surface="telegram",
            idempotency_key=(
                f"telegram:{deps.turn_id}:schedule-reminder:{input_fingerprint}"
            ),
        ),
        task=task,
        scheduled_at=resolution.utc_instant,
        timezone=resolution.timezone,
    )
    return resolution.exact_label


# ── Entry point ──


async def handle_message(deps: AgentDeps, user_message: str) -> str:
    """Handle one user message through the agentic loop.

    1. Store user message
    2. Build message history from session
    3. Run agent (model decides tools + reply)
    4. Store assistant response
    5. Return response text
    """
    user_id = deps.user["user_id"]

    # Store user message
    await deps.store.add_message(deps.session_id, user_id, "user", user_message)

    # Build message history for context
    context_builder = ContextBuilder(deps.store)
    history = await context_builder._get_truncated_messages(deps.session_id)

    # Convert to pydantic-ai message format
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    message_history: list[ModelRequest | ModelResponse] = []
    for msg in history[:-1]:  # Exclude the message we just stored (it goes as user_prompt)
        if msg["role"] == "user":
            message_history.append(
                ModelRequest(parts=[UserPromptPart(content=msg["content"])])
            )
        else:
            message_history.append(
                ModelResponse(parts=[TextPart(content=msg["content"])])
            )

    # Run the agent
    try:
        result = await amigo_agent.run(
            user_message,
            model=_get_model_name(),
            deps=deps,
            message_history=message_history if message_history else None,
        )
        response = result.output
    except Exception:
        logger.exception("Agent run failed")
        response = "Sorry, having trouble thinking right now. Try again in a minute? 🙏"

    # Store assistant response
    await deps.store.add_message(deps.session_id, user_id, "assistant", response)

    return response
