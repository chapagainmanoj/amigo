"""Reminder tools used by the app layer."""

import logging
from datetime import UTC, datetime

from src.commands.base import CommandContext
from src.commands.reminders import ReminderScheduleInput, ScheduleReminderCommand
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler
from src.utils import local_time_to_utc, utc_now

logger = logging.getLogger(__name__)


class CancelRemindersTool:
    """Acknowledge pending reminders for a task and cancel scheduled jobs."""

    name = "cancel_reminders"

    def __init__(self, store: MemoryStore, scheduler: ReminderScheduler):
        self.store = store
        self.scheduler = scheduler

    async def run(self, *, task_id: str, user_id: str) -> dict:
        reminder_ids = await self.store.acknowledge_reminders_for_task(task_id, user_id)
        for reminder_id in reminder_ids:
            self.scheduler.cancel_reminder(user_id, reminder_id)
        return {"reminder_ids": reminder_ids}


class ScheduleReminderTool:
    """Persist Reminder intent and a durable scheduler effect through one command."""

    name = "schedule_reminder"

    def __init__(self, store: MemoryStore, scheduler: ReminderScheduler):
        self.command = ScheduleReminderCommand(store)

    async def run(
        self,
        *,
        context: CommandContext,
        task: dict,
        resolved_time: str,
        timezone: str,
    ) -> dict:
        hour, minute = map(int, resolved_time.split(":"))
        send_time = local_time_to_utc(hour, minute, timezone)

        if send_time <= utc_now():
            logger.info("Skipping reminder for %s — time already passed", task["title"])
            return {"reminder": None, "scheduled_time": send_time}

        return await self.command.run(
            context,
            task_id=task["task_id"],
            schedule=ReminderScheduleInput(
                scheduled_at=send_time.replace(tzinfo=UTC),
                timezone=timezone,
            ),
        )

    async def run_at(
        self,
        *,
        user_id: str,
        reminder_id: str,
        task_title: str,
        send_time: datetime,
        chat_id: int,
    ) -> dict:
        """Schedule an existing reminder row, used by snooze callbacks."""
        self.scheduler.schedule_reminder(
            user_id=user_id,
            reminder_id=reminder_id,
            send_time=send_time,
            chat_id=chat_id,
            task_title=task_title,
        )
        return {"reminder_id": reminder_id, "scheduled_time": send_time}

    async def run_exact(
        self,
        *,
        context: CommandContext,
        task: dict,
        scheduled_at: datetime,
        timezone: str,
    ) -> dict:
        """Persist an already-confirmed full UTC/local Reminder interpretation."""
        return await self.command.run(
            context,
            task_id=task["task_id"],
            schedule=ReminderScheduleInput(
                scheduled_at=scheduled_at,
                timezone=timezone,
            ),
        )
