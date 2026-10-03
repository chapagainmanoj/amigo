"""Reusable Toolsets: every side effect a Mode can cause, grouped by domain.

A Mode receives only the Toolsets it declares, so a Tool outside them cannot be called. Each Tool
builds a CommandContext from the Tool Context and goes through the shared Commands, so Telegram,
the dashboard, and every Mode apply one set of ownership, idempotency, and version rules.

Tool names, docstrings, and signatures are the schema the model sees and a Gate A invalidating
input. Change them deliberately.
"""

import hashlib
from datetime import date

from pydantic_ai import FunctionToolset, RunContext

from src.commands.base import CommandContext, StaleVersionError
from src.commands.later import ApplyLaterCommand, LaterPolicy
from src.commands.reminders import ReminderScheduleInput, RescheduleReminderCommand
from src.commands.tasks import MoveTaskPlanningDayCommand
from src.time_resolution import TimeResolution, resolve_reminder_time
from src.tools.context import ToolContext
from src.tools.reminders import CancelRemindersTool, ScheduleReminderTool
from src.tools.tasks import CreateTaskTool, UpdateTaskStatusTool

# Retries match the single retry the Daily agent always allowed its Tools.
TASKS: FunctionToolset[ToolContext] = FunctionToolset(max_retries=1)
REMINDERS: FunctionToolset[ToolContext] = FunctionToolset(max_retries=1)

@TASKS.tool
async def create_task(
    ctx: RunContext[ToolContext],
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
            result, supplied only after the user explicitly confirms it. Always repeat the
            original reminder_time in the same call; confirmation alone is invalid.
    """
    deps = ctx.deps
    resolution = None
    if confirmed_reminder_time and not reminder_time:
        return (
            "The confirmed label must be supplied with the original reminder_time. "
            "No Task or Reminder was created."
        )
    if reminder_time:
        resolution = _resolve_time(deps, reminder_time)
        blocked = _resolution_block_message(resolution, confirmed_reminder_time)
        if blocked:
            return f"{blocked} No Task has been created."

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


@TASKS.tool
async def update_task_status(
    ctx: RunContext[ToolContext],
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


@REMINDERS.tool
async def schedule_reminder(
    ctx: RunContext[ToolContext],
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
    carried_tasks = await deps.store.get_yesterday_pending(
        deps.user["user_id"], deps.timezone
    )
    for t in [*today_tasks, *inbox_tasks, *carried_tasks]:
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


@REMINDERS.tool
async def apply_later(
    ctx: RunContext[ToolContext],
    reminder_id: str,
) -> str:
    """Apply the canonical Later policy to one active owned Reminder.

    Args:
        reminder_id: The reminder_id from the active Reminders list in context.
    """
    deps = ctx.deps
    result = await ApplyLaterCommand(
        deps.store,
        LaterPolicy(deps.clock),
    ).run(
        CommandContext(
            actor_user_id=deps.user["user_id"],
            surface="telegram",
            idempotency_key=f"telegram:{deps.turn_id}:later:{reminder_id}",
        ),
        reminder_id=reminder_id,
    )
    local_time = result["intended_local_time"][:5]
    adjustment = " after quiet hours" if result["quiet_hours_adjusted"] else ""
    return (
        f"Next reminder: {result['intended_local_date']} at {local_time} "
        f"{result['intended_timezone']}{adjustment}."
    )


@TASKS.tool
async def move_task_planning_day(
    ctx: RunContext[ToolContext],
    task_id: str,
    planning_day: date,
    expected_version: int,
) -> str:
    """Move one pending owned Task to an explicit planning date.

    Args:
        task_id: The task_id from the pending Tasks list in context.
        planning_day: Exact YYYY-MM-DD date explicitly requested by the participant.
        expected_version: The Task version shown with that task_id in context.
    """
    deps = ctx.deps
    if planning_day < deps.clock.today_in_tz(deps.timezone):
        return "Choose today or a future planning date. The Task was not changed."
    try:
        result = await MoveTaskPlanningDayCommand(deps.store).run(
            CommandContext(
                actor_user_id=deps.user["user_id"],
                surface="telegram",
                idempotency_key=f"telegram:{deps.turn_id}:move-task:{task_id}:{planning_day}",
            ),
            task_id=task_id,
            planning_day=planning_day,
            expected_version=expected_version,
        )
    except (ValueError, StaleVersionError):
        return "The Task could not be moved. Nothing was changed."
    return f"Moved '{result['task']['title']}' to {planning_day.isoformat()}."


@REMINDERS.tool
async def cancel_reminders(
    ctx: RunContext[ToolContext],
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


def _resolve_time(deps: ToolContext, expression: str) -> TimeResolution:
    return resolve_reminder_time(
        expression,
        deps.timezone,
        wake_time=deps.user.get("wake_time", "07:30"),
        sleep_time=deps.user.get("sleep_time", "23:00"),
        clock=deps.clock,
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
    deps: ToolContext,
    task: dict,
    resolution: TimeResolution,
) -> str:
    if resolution.utc_instant is None or resolution.exact_label is None:
        raise ValueError("Reminder time is not resolved")
    input_fingerprint = hashlib.sha256(
        (
            f"{task['task_id']}\0{resolution.utc_instant.isoformat()}\0"
            f"{resolution.timezone}"
        ).encode()
    ).hexdigest()[:16]
    context = CommandContext(
        actor_user_id=deps.user["user_id"],
        surface="telegram",
        idempotency_key=f"telegram:{deps.turn_id}:schedule-reminder:{input_fingerprint}",
    )
    active = [
        reminder
        for reminder in await deps.store.get_pending_reminders(deps.user["user_id"])
        if reminder["task_id"] == task["task_id"]
    ]
    if len(active) > 1:
        raise ValueError("Task has multiple active Reminders; choose one before rescheduling")
    if active:
        await RescheduleReminderCommand(deps.store, deps.clock).run(
            context,
            reminder_id=active[0]["reminder_id"],
            schedule=ReminderScheduleInput(
                scheduled_at=resolution.utc_instant,
                timezone=resolution.timezone,
            ),
        )
    else:
        await ScheduleReminderTool(deps.store, deps.scheduler, deps.clock).run_exact(
            context=context,
            task=task,
            scheduled_at=resolution.utc_instant,
            timezone=resolution.timezone,
        )
    return resolution.exact_label
