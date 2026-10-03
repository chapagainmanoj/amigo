"""Turn Context providers: reusable, public blocks a Mode can add to its instructions.

Each provider reads the Tool Context and returns one section, or None when it has nothing to say.
The runtime appends sections in the order a Mode declares them.
"""

from src.memory.context import ContextBuilder
from src.tools.context import ToolContext


def _profile_timezone(context: ToolContext) -> str:
    return context.user.get("timezone") or "UTC"


async def yesterday_summary(context: ToolContext) -> str | None:
    summary = await ContextBuilder(context.store).get_yesterday_summary(
        context.user["user_id"], _profile_timezone(context)
    )
    return f"\n<yesterday_summary>\n{summary}\n</yesterday_summary>" if summary else None


async def todays_tasks(context: ToolContext) -> str | None:
    block = await ContextBuilder(context.store).build_tasks_block(
        context.user["user_id"], _profile_timezone(context)
    )
    return f"\n<todays_tasks>\n{block}\n</todays_tasks>" if block else None


async def pending_task_ids(context: ToolContext) -> str | None:
    user_id = context.user["user_id"]
    timezone = _profile_timezone(context)
    today_tasks = await context.store.get_today_tasks(user_id, timezone)
    inbox_tasks = await context.store.get_inbox_tasks(user_id)
    carried_tasks = await context.store.get_yesterday_pending(user_id, timezone)
    pending_tasks = {
        task["task_id"]: task
        for task in [*today_tasks, *inbox_tasks, *carried_tasks]
        if task["status"] == "pending"
    }
    if not pending_tasks:
        return None
    task_lines = "\n".join(
        (
            f"- task_id={t['task_id']}: {t['title']} "
            f"(status: {t['status']}, version: {t.get('version', 1)})"
        )
        for t in pending_tasks.values()
    )
    return (
        f"\n<pending_task_ids>\n"
        f"Use these task_id values when calling update_task_status:\n"
        f"{task_lines}\n"
        f"</pending_task_ids>"
    )


async def active_reminder_ids(context: ToolContext) -> str | None:
    pending_reminders = await context.store.get_pending_reminders(context.user["user_id"])
    if not pending_reminders:
        return None
    reminder_lines = "\n".join(
        (
            f"- reminder_id={r['reminder_id']}: task_id={r['task_id']}, "
            f"{r['tasks']['title']} at {r['scheduled_time']}"
        )
        for r in pending_reminders
    )
    return (
        "\n<active_reminder_ids>\n"
        "Use these owned reminder_id values for Reminder lifecycle actions:\n"
        f"{reminder_lines}\n"
        "</active_reminder_ids>"
    )
