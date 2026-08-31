"""Canonical dashboard snapshot assembly for local and test Stores."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from src.utils import UTC, utc_now


def _datetime(value) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def build_dashboard_snapshot(
    user: dict,
    tasks: list[dict],
    reminders: list[dict],
    sessions: list[dict],
    *,
    generated_at: datetime | None = None,
) -> dict:
    """Build one tenant-scoped read model from a single Store observation."""
    now = (generated_at or utc_now()).replace(tzinfo=UTC)
    timezone = user.get("timezone") or "UTC"
    planning_day = now.astimezone(ZoneInfo(timezone)).date().isoformat()
    owned_tasks = {task["task_id"]: dict(task) for task in tasks}
    today = [task for task in owned_tasks.values() if task.get("due_date") == planning_day]
    inbox = [
        task for task in owned_tasks.values()
        if task.get("due_date") is None and task["status"] == "pending"
    ]
    carried = [
        task for task in owned_tasks.values()
        if task.get("due_date") is not None
        and task["due_date"] < planning_day
        and task["status"] == "pending"
    ]
    for population in (today, inbox, carried):
        population.sort(key=lambda item: item.get("created_at", ""), reverse=True)

    reminder_rows = []
    for reminder in reminders:
        task = owned_tasks.get(reminder["task_id"])
        if not task or reminder["status"] not in {"pending", "sending", "sent"}:
            continue
        scheduled = _datetime(reminder["scheduled_time"])
        due_date = task.get("due_date")
        population = (
            "today" if due_date == planning_day else
            "inbox" if due_date is None else
            "carried_over" if due_date < planning_day else "future"
        )
        row = dict(reminder)
        row.update(
            task={
                "task_id": task["task_id"],
                "title": task["title"],
                "category": task.get("category", "other"),
                "version": task.get("version", 1),
                "population": population,
            },
            delivery_state=(
                "overdue" if reminder["status"] == "pending" and scheduled < now
                else "scheduled" if reminder["status"] == "pending"
                else "delivering" if reminder["status"] == "sending"
                else "delivered"
            ),
        )
        reminder_rows.append(row)
    reminder_rows.sort(key=lambda item: item["scheduled_time"])

    session_rows = []
    timeout = user.get("session_timeout_minutes", 120)
    for session in sorted(sessions, key=lambda item: item["started_at"], reverse=True)[:5]:
        started = _datetime(session["started_at"])
        ended = _datetime(session["ended_at"]) if session.get("ended_at") else None
        last_activity = _datetime(session.get("last_activity_at") or session["started_at"])
        stale = ended is None and (now - last_activity).total_seconds() > timeout * 60
        state = "ended" if ended else "inactive" if stale else "active"
        row = dict(session)
        row.update(
            state=state,
            label=session.get("context_summary") or {
                "active": "Current conversation",
                "inactive": "Inactive conversation",
                "ended": "Conversation",
            }[state],
            session_type_label=(session.get("session_type") or "casual").replace("_", " ").title(),
            duration_minutes=max(0, round(((ended or now) - started).total_seconds() / 60)),
        )
        session_rows.append(row)

    return {
        "snapshot_version": str(uuid.uuid4()),
        "generated_at": now.isoformat(),
        "timezone": timezone,
        "planning_day": planning_day,
        "tasks": {"today": today, "inbox": inbox, "carried_over": carried},
        "progress": {
            "completed": sum(task["status"] == "completed" for task in today),
            "total": len(today),
        },
        "reminders": reminder_rows,
        "sessions": session_rows,
    }
