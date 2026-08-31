"""Durable scheduler-outbox projection worker."""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class SchedulerOutboxWorker:
    """Apply claimed durable effects to APScheduler using stable Reminder job identities."""

    def __init__(self, store, scheduler, *, worker_id: str = "scheduler-owner"):
        self.store = store
        self.scheduler = scheduler
        self.worker_id = worker_id

    async def drain_once(self, limit: int = 25) -> int:
        effects = await self.store.claim_scheduler_effects(limit, self.worker_id)
        completed = 0
        for effect in effects:
            try:
                await self._apply(effect)
            except Exception as error:
                logger.exception("Scheduler outbox effect %s failed", effect["effect_id"])
                await self.store.complete_scheduler_effect(
                    effect["effect_id"],
                    effect["user_id"],
                    succeeded=False,
                    error_type=type(error).__name__,
                )
                continue
            await self.store.complete_scheduler_effect(
                effect["effect_id"],
                effect["user_id"],
                succeeded=True,
                error_type=None,
            )
            completed += 1
        return completed

    async def _apply(self, effect: dict) -> None:
        if effect["effect_type"] == "schedule":
            payload = effect["payload"]
            self.scheduler.schedule_reminder(
                user_id=effect["user_id"],
                reminder_id=effect["reminder_id"],
                send_time=datetime.fromisoformat(payload["scheduled_time"]),
                chat_id=payload["telegram_chat_id"],
                task_title=payload["task_title"],
            )
            return
        if effect["effect_type"] == "cancel":
            self.scheduler.cancel_reminder(effect["user_id"], effect["reminder_id"])
            return
        raise ValueError("Unknown scheduler outbox effect")
