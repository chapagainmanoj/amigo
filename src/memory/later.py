"""Shared in-memory implementation of the atomic Later transition."""

import copy
from collections.abc import Callable

from src.utils import utc_now


def apply_later_transition(
    *,
    user: dict,
    task: dict,
    reminder: dict,
    outbox: dict[str, dict],
    new_id: Callable[[], str],
    step: int,
    scheduled_at: str,
    intended_local_date: str,
    intended_local_time: str,
    timezone: str,
    quiet_hours_adjusted: bool,
    task_due_date: str | None,
) -> dict:
    """Mutate validated in-memory state exactly as the database command will."""
    reminder["status"] = "acknowledged"
    reminder["version"] = reminder.get("version", 1) + 1
    task["version"] = task.get("version", 1) + 1
    task["deferred_count"] = task.get("deferred_count", 0) + 1
    if task_due_date:
        task["due_date"] = task_due_date

    replacement = {
        "reminder_id": new_id(),
        "task_id": task["task_id"],
        "user_id": user["user_id"],
        "scheduled_time": scheduled_at,
        "status": "pending",
        "intended_local_date": intended_local_date,
        "intended_local_time": intended_local_time,
        "intended_timezone": timezone,
        "snooze_count": step,
        "telegram_message_id": None,
        "version": 1,
    }

    effects = []
    for effect_type, effect_reminder, payload in (
        ("cancel", reminder, {}),
        (
            "schedule",
            replacement,
            {
                "scheduled_time": scheduled_at,
                "telegram_chat_id": user["telegram_chat_id"],
                "task_title": task["title"],
            },
        ),
    ):
        effect_key = f"{effect_type}:{effect_reminder['reminder_id']}"
        effect = outbox.get(effect_key)
        if not effect:
            now = utc_now().isoformat()
            effect = {
                "effect_id": new_id(),
                "effect_key": effect_key,
                "effect_type": effect_type,
                "user_id": user["user_id"],
                "task_id": task["task_id"],
                "reminder_id": effect_reminder["reminder_id"],
                "payload": payload,
                "status": "pending",
                "attempts": 0,
                "worker_id": None,
                "claimed_at": None,
                "available_at": now,
                "completed_at": None,
                "error_type": None,
                "created_at": now,
            }
            outbox[effect_key] = effect
        effects.append({"effect_id": effect["effect_id"], "effect_type": effect_type})

    return {
        "task": copy.deepcopy(task),
        "task_version": task["version"],
        "acknowledged_reminder": copy.deepcopy(reminder),
        "reminder": replacement,
        "scheduled_time": scheduled_at,
        "intended_local_date": intended_local_date,
        "intended_local_time": intended_local_time,
        "intended_timezone": timezone,
        "later_step": step,
        "quiet_hours_adjusted": quiet_hours_adjusted,
        "effect_state": "queued",
        "effects": effects,
    }
