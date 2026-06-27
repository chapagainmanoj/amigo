"""Pydantic AI agent — single tool-calling loop replaces classify→extract→resolve pipeline.

The agent sees the user message, decides which tools to call, observes results,
and produces a final reply — all in one turn. Side effects execute through injected
services (store, scheduler), keeping testability via fakes.

See ADR 0002 for rationale.
"""

import logging
from dataclasses import dataclass

import dateparser
from pydantic_ai import Agent, RunContext

from src.agent.prompts import build_system_prompt
from src.channels.base import MessageChannel
from src.memory.context import ContextBuilder
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler
from src.tools.reminders import CancelRemindersTool, ScheduleReminderTool
from src.tools.tasks import CreateTaskTool, UpdateTaskStatusTool
from src.utils import local_time_to_utc, now_in_tz, utc_now

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
    pending_tasks = [t for t in pending if t["status"] in ("pending", "deferred")]

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
) -> str:
    """Create a new task for the user.

    If reminder_time is provided this tool schedules the reminder automatically.
    Do NOT call schedule_reminder separately for the same task in the same turn —
    that would create a duplicate reminder.

    Args:
        title: Clear, actionable task title.
        category: One of: health, work, personal, social, other.
        reminder_time: Optional natural language time like "3pm", "in 10 minutes",
            "after lunch". Pass this instead of calling schedule_reminder afterwards.
    """
    deps = ctx.deps
    tool = CreateTaskTool(deps.store)
    result = await tool.run(
        user_id=deps.user["user_id"],
        title=title,
        category=category,
        session_id=deps.session_id,
        timezone=deps.timezone,
    )
    task = result["task"]

    # Schedule reminder if time was provided
    if reminder_time:
        reminder_result = await _schedule_reminder_for_task(deps, task, reminder_time)
        if reminder_result:
            return f"Created task '{title}' with reminder at {reminder_result}."
        return f"Created task '{title}' (couldn't parse reminder time '{reminder_time}')."

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
        status: One of: "done", "skipped", "deferred".
    """
    deps = ctx.deps
    cancel_tool = CancelRemindersTool(deps.store, deps.scheduler)
    tool = UpdateTaskStatusTool(deps.store, cancel_tool)
    result = await tool.run(
        task_id=task_id,
        status=status,
        user_id=deps.user["user_id"],
    )
    task_title = result["task"].get("title", "task")
    return f"Updated '{task_title}' to {status}."


@amigo_agent.tool
async def schedule_reminder(
    ctx: RunContext[AgentDeps],
    task_id: str,
    time_expression: str,
) -> str:
    """Schedule or reschedule a reminder for an already-created task.

    Use this only when the task was created without a reminder_time, or when
    the user wants to change the time of an existing reminder. Do NOT call this
    after create_task(reminder_time=...) — the reminder is already set.

    Args:
        task_id: The task_id to schedule a reminder for.
        time_expression: Natural language time like "3pm", "in 30 minutes", "after lunch".
    """
    deps = ctx.deps
    task = None
    today_tasks = await deps.store.get_today_tasks(deps.user["user_id"], deps.timezone)
    for t in today_tasks:
        if t["task_id"] == task_id:
            task = t
            break

    if not task:
        return f"Task {task_id} not found."

    result = await _schedule_reminder_for_task(deps, task, time_expression)
    if result:
        return f"Reminder scheduled for '{task['title']}' at {result}."
    return f"Couldn't parse time '{time_expression}'."


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


def parse_time_expression(time_expr: str, timezone: str) -> str | None:
    """Parse natural language time to HH:MM using dateparser.

    Returns HH:MM string or None if unparseable.
    """
    settings = {
        "TIMEZONE": timezone,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": now_in_tz(timezone).replace(tzinfo=None),
    }
    parsed = dateparser.parse(time_expr, settings=settings)
    if parsed is None:
        return None
    return parsed.strftime("%H:%M")


async def _schedule_reminder_for_task(
    deps: AgentDeps, task: dict, time_expr: str
) -> str | None:
    """Parse time and schedule a reminder. Returns resolved time or None."""
    resolved = parse_time_expression(time_expr, deps.timezone)
    if not resolved:
        logger.warning("Could not parse time expression: %s", time_expr)
        return None

    try:
        hour, minute = map(int, resolved.split(":"))
        send_time = local_time_to_utc(hour, minute, deps.timezone)

        if send_time <= utc_now():
            logger.info("Skipping reminder for %s — time already passed", task["title"])
            return None

        tool = ScheduleReminderTool(deps.store, deps.scheduler)
        await tool.run(
            user_id=deps.user["user_id"],
            task=task,
            resolved_time=resolved,
            timezone=deps.timezone,
            chat_id=deps.chat_id,
        )
        return resolved
    except Exception:
        logger.exception("Failed to schedule reminder for '%s'", task["title"])
        return None


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
