"""APScheduler reminder management — in-memory for Phase 1a."""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.bot.keyboards import reminder_keyboard
from src.channels.base import MessageChannel
from src.memory.store import MemoryStore
from src.utils import Clock, default_clock

logger = logging.getLogger(__name__)

# Reminders missed by less than this window still fire on restart
MISSED_FIRE_WINDOW = timedelta(minutes=15)


class ReminderScheduler:
    """Manages scheduled reminders via APScheduler.

    Phase 1a: in-memory job store, reloads from Supabase on restart.
    Phase 1b: Redis job store for persistence.

    Uses stable job IDs (user_id:reminder_id) for idempotency.
    """

    def __init__(self, channel: MessageChannel, store: MemoryStore, clock: Clock = default_clock):
        self.scheduler = AsyncIOScheduler()
        self.channel = channel
        self.store = store
        self.clock = clock

    def start(self) -> None:
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Reminder scheduler started")

    async def reload_pending(self) -> None:
        """Reload pending reminders from Supabase after restart.

        Queries all pending reminders, re-schedules future ones,
        and fires recently-missed ones (within 15-min window).
        """
        now = self.clock.utc_now()
        cutoff = now - MISSED_FIRE_WINDOW

        reminders = await self.store.get_pending_reminders_for_reload(cutoff)

        count = 0
        for reminder in reminders:
            chat_id = reminder.get("user_profiles", {}).get("telegram_chat_id")
            task_title = reminder.get("tasks", {}).get("title", "your task")

            if not chat_id:
                logger.warning("Skipping reminder %s — no chat_id", reminder["reminder_id"])
                continue

            scheduled = datetime.fromisoformat(reminder["scheduled_time"])
            # Normalize to naive UTC to match clock.utc_now()
            if scheduled.tzinfo is not None:
                scheduled = scheduled.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

            if scheduled <= now:
                # Missed but within window — fire immediately
                logger.info(
                    "Firing missed reminder %s (was scheduled %s)",
                    reminder["reminder_id"],
                    scheduled,
                )
                send_time = now + timedelta(seconds=5)
            else:
                send_time = scheduled

            self.schedule_reminder(
                user_id=reminder["user_id"],
                reminder_id=reminder["reminder_id"],
                send_time=send_time,
                chat_id=chat_id,
                task_title=task_title,
            )
            count += 1

        logger.info("Reloaded %d pending reminders from database", count)

    def shutdown(self) -> None:
        """Gracefully stop the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Reminder scheduler stopped")

    def schedule_reminder(
        self,
        user_id: str,
        reminder_id: str,
        send_time: datetime,
        chat_id: int,
        task_title: str,
    ) -> None:
        """Schedule a reminder notification.

        Uses stable job ID for idempotency — safe to call multiple times.
        """
        job_id = f"{user_id}:{reminder_id}"

        self.scheduler.add_job(
            self._send_reminder,
            trigger="date",
            run_date=send_time,
            id=job_id,
            replace_existing=True,
            kwargs={
                "chat_id": chat_id,
                "reminder_id": reminder_id,
                "task_title": task_title,
            },
        )
        logger.info("Scheduled reminder %s at %s for '%s'", job_id, send_time, task_title)

    def cancel_reminder(self, user_id: str, reminder_id: str) -> None:
        """Cancel a scheduled reminder."""
        job_id = f"{user_id}:{reminder_id}"
        try:
            self.scheduler.remove_job(job_id)
            logger.info("Cancelled reminder %s", job_id)
        except Exception:
            logger.debug("Reminder %s not found in scheduler (may have already fired)", job_id)

    async def _send_reminder(
        self, chat_id: int, reminder_id: str, task_title: str
    ) -> None:
        """Fire a reminder — send Telegram message with Done/Skip/Later buttons.

        Guards against stale reminders: checks reminder status and task status
        before sending. Skips silently if task was already completed.
        """
        try:
            # Guard: atomically claim the reminder before sending so deploy overlap
            # or accidental scale-out cannot send the same reminder twice.
            reminder = await self.store.claim_reminder_for_send(reminder_id)
            if not reminder:
                return
            task_status = reminder.get("tasks", {}).get("status")
            if task_status in ("done", "skipped"):
                logger.debug("Skipping reminder %s — task already %s", reminder_id, task_status)
                await self.store.update_reminder(reminder_id, {"status": "acknowledged"})
                return

            try:
                message_id = await self.channel.send_message(
                    chat_id,
                    f"Hey — you mentioned wanting to \"{task_title}\" today. Good time? 📋",
                    buttons=reminder_keyboard(reminder_id),
                )
            except Exception:
                await self.store.update_reminder(reminder_id, {"status": "pending"})
                raise

            # Store telegram_message_id for later button editing
            if message_id:
                await self.store.update_reminder(reminder_id, {
                    "status": "sent",
                    "telegram_message_id": message_id,
                })

        except Exception:
            logger.exception("Failed to send reminder %s", reminder_id)
