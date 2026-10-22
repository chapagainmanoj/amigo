"""Reminder persistence invariants shared by Store implementations."""

from datetime import UTC, datetime

REMINDER_MUTABLE_FIELDS = {
    "follow_up_sent",
    "scheduled_time",
    "snooze_count",
    "status",
    "telegram_message_id",
}


def validate_reminder_updates(updates: dict) -> None:
    """Reject attempts to rewrite Reminder identity or ownership fields."""
    if not updates or not set(updates).issubset(REMINDER_MUTABLE_FIELDS):
        raise ValueError("Invalid reminder update")



def validate_reminder_timing(reminder: dict, updates: dict) -> None:
    """Changing an instant requires canonical rescheduling with a fresh Reminder identity."""
    if "scheduled_time" not in updates:
        return
    try:
        old = datetime.fromisoformat(reminder["scheduled_time"])
        new = datetime.fromisoformat(updates["scheduled_time"])
        old = old.replace(tzinfo=UTC) if old.tzinfo is None else old.astimezone(UTC)
        new = new.replace(tzinfo=UTC) if new.tzinfo is None else new.astimezone(UTC)
    except (TypeError, ValueError):
        raise ValueError("Reminder timing is immutable; use the reschedule command") from None
    if old != new:
        raise ValueError("Reminder timing is immutable; use the reschedule command")
