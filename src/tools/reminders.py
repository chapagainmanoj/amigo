"""Reminder tools used by the app layer."""

import logging
from datetime import datetime

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
    """Persist a reminder and schedule its delivery."""

    name = "schedule_reminder"

    def __init__(self, store: MemoryStore, scheduler: ReminderScheduler):
        self.store = store
        self.scheduler = scheduler

    async def run(
        self,
        *,
        user_id: str,
        task: dict,
        resolved_time: str,
        timezone: str,
        chat_id: int,
    ) -> dict:
        hour, minute = map(int, resolved_time.split(":"))
        send_time = local_time_to_utc(hour, minute, timezone)

        if send_time <= utc_now():
            logger.info("Skipping reminder for %s — time already passed", task["title"])
            return {"reminder": None, "scheduled_time": send_time}

        # Invariant: a task has at most one pending reminder at a time.
        # Cancel any existing pending reminders before creating a new one.
        # This naturally handles both duplicate scheduling within a single agent
        # turn and explicit user reschedule requests.
        existing_ids = await self.store.acknowledge_reminders_for_task(
            task["task_id"], user_id
        )
        for rid in existing_ids:
            self.scheduler.cancel_reminder(user_id, rid)
        if existing_ids:
            logger.info(
                "Replaced %d existing pending reminder(s) for task %s",
                len(existing_ids),
                task["task_id"],
            )

        reminder = await self.store.create_reminder(
            task_id=task["task_id"],
            user_id=user_id,
            scheduled_time=send_time.isoformat(),
        )
        self.scheduler.schedule_reminder(
            user_id=user_id,
            reminder_id=reminder["reminder_id"],
            send_time=send_time,
            chat_id=chat_id,
            task_title=task["title"],
        )
        return {"reminder": reminder, "scheduled_time": send_time}

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
