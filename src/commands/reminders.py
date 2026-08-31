"""Canonical Reminder application commands."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.commands.base import CommandContext
from src.utils import utc_now


@dataclass(frozen=True)
class ReminderScheduleInput:
    """Exact Reminder timing input; participant identity is intentionally absent."""

    scheduled_at: datetime
    timezone: str


class ScheduleReminderCommand:
    """Schedule an owned Task Reminder and durable projection effect atomically."""

    def __init__(self, store):
        self.store = store

    async def run(
        self,
        context: CommandContext,
        *,
        task_id: str,
        schedule: ReminderScheduleInput,
    ) -> dict:
        timing = _normalize_timing(schedule)
        payload_hash = _payload_hash(
            context,
            "schedule_reminder",
            {"task_id": task_id, **timing},
        )
        return await self.store.schedule_reminder_command(
            user_id=context.actor_user_id,
            idempotency_key=context.idempotency_key,
            payload_hash=payload_hash,
            task_id=task_id,
            replace_reminder_id=None,
            **timing,
        )


class RescheduleReminderCommand:
    """Replace an owned active Reminder with a newly scheduled Reminder."""

    def __init__(self, store):
        self.store = store

    async def run(
        self,
        context: CommandContext,
        *,
        reminder_id: str,
        schedule: ReminderScheduleInput,
    ) -> dict:
        timing = _normalize_timing(schedule)
        payload_hash = _payload_hash(
            context,
            "reschedule_reminder",
            {"reminder_id": reminder_id, **timing},
        )
        return await self.store.schedule_reminder_command(
            user_id=context.actor_user_id,
            idempotency_key=context.idempotency_key,
            payload_hash=payload_hash,
            task_id=None,
            replace_reminder_id=reminder_id,
            **timing,
        )


class CancelReminderCommand:
    """Cancel an owned Reminder and queue cancellation of its scheduler projection."""

    def __init__(self, store):
        self.store = store

    async def run(
        self,
        context: CommandContext,
        *,
        reminder_id: str,
    ) -> dict:
        payload_hash = _payload_hash(
            context,
            "cancel_reminder",
            {"reminder_id": reminder_id},
        )
        return await self.store.cancel_reminder_command(
            user_id=context.actor_user_id,
            idempotency_key=context.idempotency_key,
            payload_hash=payload_hash,
            reminder_id=reminder_id,
        )


def _normalize_timing(schedule: ReminderScheduleInput) -> dict[str, str]:
    scheduled_at = schedule.scheduled_at
    if scheduled_at.tzinfo is None or scheduled_at.utcoffset() is None:
        raise ValueError("Reminder time must include a timezone offset")
    if scheduled_at.astimezone(UTC) <= utc_now().replace(tzinfo=UTC):
        raise ValueError("Reminder time must be in the future")
    try:
        timezone = ZoneInfo(schedule.timezone)
    except ZoneInfoNotFoundError:
        raise ValueError("Invalid Reminder timezone") from None

    intended = scheduled_at.astimezone(timezone)
    return {
        "scheduled_time": scheduled_at.astimezone(ZoneInfo("UTC")).isoformat(),
        "intended_local_date": intended.date().isoformat(),
        "intended_local_time": intended.time().replace(tzinfo=None).isoformat(),
        "intended_timezone": schedule.timezone,
    }


def _payload_hash(
    context: CommandContext,
    command: str,
    command_input: dict,
) -> str:
    payload = {
        "command": command,
        "surface": context.surface,
        "input": command_input,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
