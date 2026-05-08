"""Reminder scheduling and inline callback actions."""

import logging
from datetime import timedelta

from src.agent.amigo import AmigoAgent
from src.channels.base import MessageChannel
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler
from src.utils import local_time_to_utc, utc_now

logger = logging.getLogger(__name__)

SNOOZE_DELAYS_MINUTES = [60, 30]


class ReminderActions:
    """Coordinates task reminder persistence, scheduling, and callbacks."""

    def __init__(
        self,
        agent: AmigoAgent,
        channel: MessageChannel,
        store: MemoryStore,
        scheduler: ReminderScheduler,
    ):
        self.agent = agent
        self.channel = channel
        self.store = store
        self.scheduler = scheduler

    async def schedule_for_task(
        self, user: dict, task: dict, time_expr: str, chat_id: int
    ) -> None:
        """Resolve a time expression and schedule a reminder in UTC."""
        try:
            tz = user.get("timezone") or "UTC"
            resolution = await self.agent.resolve_reminder_time(time_expr, tz)

            hour, minute = map(int, resolution.resolved_time.split(":"))
            send_time = local_time_to_utc(hour, minute, tz)

            if send_time <= utc_now():
                logger.info("Skipping reminder for %s — time already passed", task["title"])
                return

            reminder = await self.store.create_reminder(
                task_id=task["task_id"],
                user_id=user["user_id"],
                scheduled_time=send_time.isoformat(),
            )
            self.scheduler.schedule_reminder(
                user_id=user["user_id"],
                reminder_id=reminder["reminder_id"],
                send_time=send_time,
                chat_id=chat_id,
                task_title=task["title"],
            )
        except Exception:
            logger.exception("Failed to schedule reminder for task: %s", task["title"])

    async def cancel_for_task(self, task_id: str, user_id: str) -> None:
        """Acknowledge all pending reminders for a task and cancel scheduler jobs."""
        reminder_ids = await self.store.acknowledge_reminders_for_task(task_id, user_id)
        for reminder_id in reminder_ids:
            self.scheduler.cancel_reminder(user_id, reminder_id)

    async def handle_callback(self, chat_id: int, message_id: int, data: str) -> None:
        """Handle Done/Skip/Later reminder button callbacks."""
        parts = data.split(":", 1)
        if len(parts) != 2:
            return

        action, reminder_id = parts

        user = await self.store.get_user_by_chat_id(chat_id)
        if not user:
            return

        reminder = await self.store.get_reminder_with_task(reminder_id)
        if not reminder or reminder["user_id"] != user["user_id"]:
            logger.warning(
                "Callback ownership mismatch: chat %s, reminder %s",
                chat_id,
                reminder_id,
            )
            return

        await self.channel.edit_message_buttons(chat_id, message_id, buttons=None)

        if action == "done":
            await self.store.update_task_status(reminder["task_id"], "done")
            await self.cancel_for_task(reminder["task_id"], reminder["user_id"])
            await self.channel.send_message(
                chat_id, f"✅ Nice — \"{reminder['tasks']['title']}\" done!"
            )

        elif action == "skip":
            await self.store.update_task_status(reminder["task_id"], "skipped")
            await self.cancel_for_task(reminder["task_id"], reminder["user_id"])
            await self.channel.send_message(chat_id, "Skipped ⏭️")

        elif action == "later":
            await self._handle_later(chat_id, reminder_id, reminder)

    async def _handle_later(self, chat_id: int, reminder_id: str, reminder: dict) -> None:
        """Apply the Phase 1a snooze policy."""
        snooze_count = reminder.get("snooze_count", 0)

        if snooze_count >= len(SNOOZE_DELAYS_MINUTES):
            await self.store.update_task_status(reminder["task_id"], "deferred")
            await self.store.update_reminder(reminder_id, {"status": "acknowledged"})
            await self.channel.send_message(
                chat_id, "Got it — I'll bring it up tomorrow morning."
            )
            return

        delay = SNOOZE_DELAYS_MINUTES[snooze_count]
        new_time = utc_now() + timedelta(minutes=delay)
        await self.store.update_reminder(reminder_id, {
            "snooze_count": snooze_count + 1,
            "scheduled_time": new_time.isoformat(),
            "status": "pending",
        })
        self.scheduler.schedule_reminder(
            user_id=str(reminder["user_id"]),
            reminder_id=reminder_id,
            send_time=new_time,
            chat_id=chat_id,
            task_title=reminder["tasks"]["title"],
        )
        await self.channel.send_message(chat_id, f"⏰ I'll remind you in {delay} min.")
