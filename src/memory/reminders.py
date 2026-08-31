"""Reminder persistence invariants shared by Store implementations."""

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

