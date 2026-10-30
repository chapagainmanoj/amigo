"""APScheduler reminder management — in-memory for Phase 1a."""

import contextlib
import hashlib
import logging
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.bot.keyboards import reminder_keyboard
from src.channels.base import MessageChannel, Recipient
from src.channels.delivery import proactive_recipient, reachable_here
from src.memory.proactive import instant
from src.memory.store import MemoryStore
from src.utils import Clock, default_clock

logger = logging.getLogger(__name__)

# Reminders missed by less than this window still fire on restart
MISSED_FIRE_WINDOW = timedelta(minutes=15)
RECONCILIATION_INTERVAL_SECONDS = 60
# An unfinished delivery attempt younger than this may still be in flight: reconciliation runs
# every minute alongside live sends, so it only settles attempts a crash or restart abandoned.
DELIVERY_ATTEMPT_LEASE = timedelta(minutes=2)
POLLING_INTERVAL_SECONDS = 10
_SYSTEM_JOB_IDS = {
    "scheduler-outbox-worker", "scheduler-reconciliation", "mode-conversation-maintenance",
}
SCHEDULER_OWNER_KEY = "beta-scheduler"


def _attempt_expired(attempt: dict, now: datetime) -> bool:
    started = attempt.get("started_at")
    if not started:
        return True
    started_at = datetime.fromisoformat(started) if isinstance(started, str) else started
    if started_at.tzinfo is not None:
        started_at = started_at.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return now - started_at >= DELIVERY_ATTEMPT_LEASE


class ReminderScheduler:
    """Manages scheduled reminders via APScheduler.

    Phase 1a: in-memory job store, reloads from Supabase on restart.
    Phase 1b: Redis job store for persistence.

    Uses stable job IDs (user_id:reminder_id) for idempotency.
    """

    def __init__(self, channel: MessageChannel, store: MemoryStore, clock: Clock = default_clock):
        self.scheduler = AsyncIOScheduler(timezone=ZoneInfo("UTC"))
        self.channel = channel
        self.store = store
        self.clock = clock
        self.worker_id = str(uuid.uuid4())
        self._mode_conversations = None

    def start(self) -> None:
        """Start the scheduler."""
        self.scheduler.start()
        logger.info("Reminder scheduler started")

    async def reload_pending(self) -> None:
        """Compatibility entrypoint for the authoritative reconciliation pass."""
        await self.reconcile()

    async def reconcile(self) -> dict[str, int]:
        """Make APScheduler converge on authoritative Reminder rows."""
        now = self.clock.utc_now()
        cutoff = now - MISSED_FIRE_WINDOW
        reminders = await self.store.get_reminders_for_reconciliation()
        desired_jobs: set[str] = set()
        delayed: dict[tuple[str, int], list[dict]] = {}
        report = {
            "scheduled": 0,
            "recovered": 0,
            "missed": 0,
            "failed": 0,
            "cancelled": 0,
            "missing_jobs": 0,
            "wrong_time_jobs": 0,
        }

        for reminder in reminders:
            user_id = reminder["user_id"]
            reminder_id = reminder["reminder_id"]
            profile = reminder.get("user_profiles") or {}
            # A scheduling hint only; delivery re-resolves the address when the job fires.
            chat_id = profile.get("telegram_chat_id")
            task = reminder.get("tasks") or {}
            if (
                not reachable_here(self.channel, {"user_id": user_id, **profile})
                or task.get("user_id") != user_id
                or task.get("status") != "pending"
                or reminder["status"] == "sent"
            ):
                continue

            if reminder["status"] == "sending":
                occurrence = reminder.get("reminder_occurrences") or {}
                if isinstance(occurrence, list):
                    occurrence = occurrence[0] if occurrence else {}
                attempts = occurrence.get("reminder_delivery_attempts") or []
                unfinished = next(
                    (
                        attempt
                        for attempt in sorted(
                            attempts,
                            key=lambda item: item.get("attempt_number", 0),
                            reverse=True,
                        )
                        if attempt.get("finished_at") is None
                    ),
                    None,
                )
                if unfinished and not _attempt_expired(unfinished, now):
                    continue
                if unfinished:
                    await self.store.finish_reminder_delivery(
                        attempt_id=unfinished["attempt_id"],
                        reminder_id=reminder_id,
                        user_id=user_id,
                        result="error",
                        normalized_cause="interrupted_delivery_unknown",
                        retry_decision="do_not_retry",
                        **self._delivery_proof(None),
                    )
                    report["failed"] += 1
                    continue
                await self.store.update_reminder(reminder_id, {"status": "pending"}, user_id)
                reminder["status"] = "pending"
                report["recovered"] += 1

            scheduled = datetime.fromisoformat(reminder["scheduled_time"])
            if scheduled.tzinfo is not None:
                scheduled = scheduled.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

            if scheduled < cutoff:
                await self.store.update_reminder(reminder_id, {"status": "missed"}, user_id)
                report["missed"] += 1
                continue
            if scheduled <= now:
                delayed.setdefault((user_id, chat_id), []).append(reminder)
                continue

            job_id = f"{user_id}:{reminder_id}"
            existing_job = self.scheduler.get_job(job_id)
            if existing_job is None:
                report["missing_jobs"] += 1
            elif existing_job.trigger.run_date.replace(tzinfo=None) != scheduled:
                report["wrong_time_jobs"] += 1
            self.schedule_reminder(user_id, reminder_id, scheduled, chat_id, task["title"])
            desired_jobs.add(job_id)
            report["scheduled"] += 1

        for (user_id, chat_id), late_reminders in delayed.items():
            job_id = f"recovery:{user_id}"
            self._schedule_recovery_summary(user_id, chat_id, late_reminders, now, job_id)
            desired_jobs.add(job_id)

        for job in list(self.scheduler.get_jobs()):
            if job.id in _SYSTEM_JOB_IDS or job.id in desired_jobs:
                continue
            self.scheduler.remove_job(job.id)
            report["cancelled"] += 1

        await self.store.record_scheduler_heartbeat(
            owner_key=SCHEDULER_OWNER_KEY,
            worker_id=self.worker_id,
            missing_jobs=report["missing_jobs"],
            wrong_time_jobs=report["wrong_time_jobs"],
            inverse_drift_jobs=report["cancelled"],
        )

        logger.info("Reminder reconciliation summary: %s", report)
        return report

    def shutdown(self) -> None:
        """Gracefully stop the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("Reminder scheduler stopped")

    def start_outbox_worker(self, callback) -> None:
        """Poll durable scheduler effects through the single scheduler owner."""
        self.scheduler.add_job(
            callback,
            trigger="interval",
            seconds=POLLING_INTERVAL_SECONDS,
            id="scheduler-outbox-worker",
            replace_existing=True,
            max_instances=1,
        )

    def start_reconciliation(self, callback) -> None:
        """Run the convergence pass periodically under the single scheduler owner."""
        self.scheduler.add_job(
            callback,
            trigger="interval",
            seconds=RECONCILIATION_INTERVAL_SECONDS,
            id="scheduler-reconciliation",
            replace_existing=True,
            max_instances=1,
        )

    async def start_mode_maintenance(self, callback) -> None:
        """Close expired Mode conversations without coupling the scheduler to a transport."""
        self.scheduler.add_job(
            callback,
            trigger="interval",
            seconds=RECONCILIATION_INTERVAL_SECONDS,
            id="mode-conversation-maintenance",
            replace_existing=True,
            max_instances=1,
        )

    async def _daily_delivery(self, user_id: str):
        """Resolve the current Daily address at delivery time, never from outbox payloads."""
        from src.conversations import ModeConversationService

        user = await self.store.get_user_by_id(user_id)
        if not user or user["user_id"] != user_id:
            raise ValueError("Reminder endpoint no longer belongs to its participant")
        if not reachable_here(self.channel, user):
            raise ValueError("Reminder channel is not the participant's primary channel")
        chat_id = await proactive_recipient(self.channel, user)
        if chat_id is None:
            raise ValueError("Participant has no linked messaging endpoint")
        if self._mode_conversations is None:
            self._mode_conversations = ModeConversationService(self.store, self.channel)
        conversation = await self._mode_conversations.ensure(user, "daily", chat_id=chat_id)
        return chat_id, conversation

    def _schedule_recovery_summary(
        self,
        user_id: str,
        chat_id: Recipient,
        reminders: list[dict],
        now: datetime,
        job_id: str,
    ) -> None:
        with contextlib.suppress(Exception):
            self.scheduler.remove_job(job_id)
        self.scheduler.add_job(
            self._send_recovery_summary,
            trigger="date",
            run_date=now + timedelta(seconds=5),
            id=job_id,
            replace_existing=True,
            kwargs={"user_id": user_id, "chat_id": chat_id, "reminders": reminders},
        )

    async def _send_recovery_summary(
        self, user_id: str, chat_id: Recipient, reminders: list[dict]
    ) -> None:
        user = await self.store.get_user_by_id(user_id)
        if not user:
            return
        local = instant(self.clock.utc_now()).astimezone(ZoneInfo(user.get("timezone") or "UTC"))
        scheduled_at = local.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        identities = ",".join(sorted(row["reminder_id"] for row in reminders))
        identity_hash = hashlib.sha256(identities.encode()).hexdigest()[:32]
        delivery_key = f"recovery:{local.date().isoformat()}:{identity_hash}"
        reserved = await self.store.reserve_proactive_delivery(
            user_id, delivery_key, "recovery", scheduled_at
        )
        if (
            reserved["status"] == "budget_exhausted"
            or reserved["reservation"]["state"] != "reserved"
        ):
            return
        claimed: list[tuple[dict, str]] = []
        dispatched = False
        try:
            chat_id, conversation = await self._daily_delivery(user_id)
            # Atomic transition fences concurrent recovery workers and crash replay.
            if not await self.store.mark_proactive_dispatch(user_id, delivery_key):
                return
            dispatched = True
            for reminder in reminders:
                row = await self.store.claim_reminder_for_send(
                    reminder["reminder_id"], user_id,
                    f"recovery:{reminder['reminder_id']}:{uuid.uuid4()}",
                )
                if row:
                    claimed.append((reminder, row["attempt"]["attempt_id"]))
            if not claimed:
                await self.store.finish_proactive_delivery(user_id, delivery_key, "rejected")
                return
            titles = [item.get("tasks", {}).get("title", "your task") for item, _ in claimed]
            text = "A few reminders were delayed while Amigo restarted:\n" + "\n".join(
                f"• {title}" for title in titles
            )
            message_id = await self.channel.send_message(
                chat_id, text, conversation=conversation,
            )
            await self.store.finish_proactive_delivery(
                user_id, delivery_key, "accepted" if message_id is not None else "rejected"
            )
        except Exception as error:
            if dispatched:
                await self.store.finish_proactive_delivery(user_id, delivery_key, "uncertain")
            else:
                await self.store.release_proactive_delivery(user_id, delivery_key)
            for reminder, attempt_id in claimed:
                await self.store.finish_reminder_delivery(
                    attempt_id=attempt_id,
                    reminder_id=reminder["reminder_id"], user_id=user_id,
                    result="timeout" if isinstance(error, TimeoutError) else "error",
                    normalized_cause=type(error).__name__, retry_decision="do_not_retry",
                    **self._delivery_proof(None),
                )
            raise
        for reminder, attempt_id in claimed:
            await self._finish_provider_result(
                attempt_id=attempt_id, reminder_id=reminder["reminder_id"],
                user_id=user_id, message_id=message_id,
            )

    def schedule_reminder(
        self,
        user_id: str,
        reminder_id: str,
        send_time: datetime,
        chat_id: Recipient | None,
        task_title: str,
    ) -> None:
        """Schedule a reminder notification.

        Uses stable job ID for idempotency — safe to call multiple times.
        """
        job_id = f"{user_id}:{reminder_id}"

        # Explicitly remove any existing job before adding. APScheduler's
        # replace_existing=True only works after start() when the jobstore
        # is initialised; before start(), pending jobs bypass the lookup.
        with contextlib.suppress(Exception):
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(
            self._send_reminder,
            trigger="date",
            run_date=send_time,
            id=job_id,
            replace_existing=True,
            kwargs={
                "user_id": user_id,
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
        self, user_id: str, chat_id: Recipient, reminder_id: str, task_title: str
    ) -> None:
        """Fire a reminder — send Telegram message with Done/Skip/Later buttons.

        Guards against stale reminders: checks reminder status and task status
        before sending. Skips silently if task was already completed.
        """
        try:
            # Guard: atomically claim the reminder before sending so deploy overlap
            # or accidental scale-out cannot send the same reminder twice.
            reminder = await self.store.claim_reminder_for_send(
                reminder_id,
                user_id,
                f"delivery:{reminder_id}:{uuid.uuid4()}",
            )
            if not reminder:
                return
            attempt_id = reminder["attempt"]["attempt_id"]

            try:
                chat_id, conversation = await self._daily_delivery(user_id)
                message_id = await self.channel.send_message(
                    chat_id,
                    f"Hey — you mentioned wanting to \"{task_title}\" today. Good time? 📋",
                    buttons=reminder_keyboard(reminder_id),
                    conversation=conversation,
                )
            except Exception as error:
                await self.store.finish_reminder_delivery(
                    attempt_id=attempt_id,
                    reminder_id=reminder_id,
                    user_id=user_id,
                    result="timeout" if isinstance(error, TimeoutError) else "error",
                    normalized_cause=type(error).__name__,
                    retry_decision="do_not_retry",
                    **self._delivery_proof(None),
                )
                raise

            await self._finish_provider_result(
                attempt_id=attempt_id,
                reminder_id=reminder_id,
                user_id=user_id,
                message_id=message_id,
            )

        except Exception:
            logger.exception("Failed to send reminder %s", reminder_id)

    async def _finish_provider_result(
        self,
        *,
        attempt_id: str,
        reminder_id: str,
        user_id: str,
        message_id: int | None,
    ) -> None:
        """Normalize provider acceptance into one immutable attempt outcome."""
        accepted = message_id is not None
        await self.store.finish_reminder_delivery(
            attempt_id=attempt_id,
            reminder_id=reminder_id,
            user_id=user_id,
            result="accepted" if accepted else "rejected",
            normalized_cause=None if accepted else "missing_provider_message_id",
            retry_decision="do_not_retry",
            **self._delivery_proof(message_id),
        )

    def _delivery_proof(self, message_id: int | str | None) -> dict:
        """Provider acceptance recorded against the channel that actually sent it."""
        channel = getattr(self.channel, "channel_id", "telegram")
        return {
            "telegram_message_id": message_id if channel == "telegram" else None,
            "channel": channel,
            "channel_message_ref": None if message_id is None else str(message_id),
        }
