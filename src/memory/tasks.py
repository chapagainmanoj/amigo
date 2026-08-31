"""Canonical Task lifecycle validation."""

TASK_STATUSES = frozenset({"pending", "completed", "skipped", "cancelled"})


def validate_task_status(status: str) -> None:
    """Reject legacy or unknown Task lifecycle states."""
    if status not in TASK_STATUSES:
        raise ValueError("Invalid Task status")
