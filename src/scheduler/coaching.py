"""Durable, bounded coaching delivery; disabled until reviewed admission is explicitly enabled."""

import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.channels.delivery import proactive_recipient, reachable_here
from src.memory.proactive import instant
from src.utils import default_clock

logger = logging.getLogger(__name__)

LATE_WINDOW = timedelta(minutes=15)


def _quiet(local, wake, sleep):
    wake, sleep = time.fromisoformat(wake), time.fromisoformat(sleep)
    wall = local.time().replace(tzinfo=None)
    return not (wake <= wall < sleep if wake < sleep else wall >= wake or wall < sleep)


def plan_coaching_delivery(program, user, now, history):
    """One selected slot/day; earliest DST fold, no nonexistent time, no late catch-up."""
    now = instant(now)
    if program["state"] != "active" or not instant(program["starts_at"]) <= now < instant(
        program["ends_at"]
    ):
        return None
    zone = ZoneInfo(program["timezone"])
    local = now.astimezone(zone)
    profile_local = now.astimezone(ZoneInfo(user.get("timezone") or "UTC"))
    if local.isoweekday() not in program["check_in_days"] or _quiet(
        profile_local, user.get("wake_time") or "07:30", user.get("sleep_time") or "23:00"
    ):
        return None
    wall = datetime.combine(local.date(), time.fromisoformat(program["check_in_time"]))
    candidates = [
        wall.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        for fold in (0, 1)
        if wall.replace(tzinfo=zone, fold=fold)
        .astimezone(UTC)
        .astimezone(zone)
        .replace(tzinfo=None)
        == wall
    ]
    if not candidates:
        return None
    scheduled = min(candidates)
    if not scheduled <= now <= scheduled + LATE_WINDOW:
        return None
    day = local.date().isoformat()
    deliveries = history.get("deliveries", [])
    if any(row["local_day"] == day for row in deliveries):
        return None
    reply = instant(history["last_reply_at"]) if history.get("last_reply_at") else None
    unanswered = [
        row
        for row in deliveries
        if row["state"] in {"accepted", "uncertain", "dispatched"}
        and (reply is None or instant(row.get("dispatched_at") or row["scheduled_at"]) > reply)
    ]
    if len(unanswered) >= 2:
        return None
    if unanswered:
        kind = "follow_up"
    else:
        start_day = instant(program["starts_at"]).astimezone(zone).date()
        elapsed = (local.date() - start_day).days + 1
        week = elapsed // 7
        reviewed = any(
            row["kind"] == "weekly_review"
            and row["state"] in {"accepted", "uncertain", "dispatched"}
            and (datetime.fromisoformat(row["local_day"]).date() - start_day).days + 1 >= week * 7
            for row in deliveries
        )
        kind = "weekly_review" if week >= 1 and not reviewed else "check_in"
    return dict(
        delivery_key=f"coach:{program['program_id']}:{day}",
        local_day=day,
        kind=kind,
        scheduled_at=scheduled.isoformat(),
    )


class CoachingDeliveryWorker:
    def __init__(
        self,
        store,
        channel,
        *,
        clock=default_clock,
        admission_enabled=False,
        admission_check=None,
    ):
        self.store = store
        self.channel = channel
        self.clock = clock
        self.admission_enabled = admission_enabled
        self.admission_check = admission_check
        self.worker_id = str(uuid.uuid4())

    async def _admitted(self):
        if not self.admission_enabled:
            return False
        if self.admission_check is None:
            return self.admission_enabled is True
        try:
            allowed = await self.admission_check()
        except Exception:
            return False
        return self.admission_enabled is True and allowed is True

    async def reconcile(self):
        await self.store.complete_due_coaching_programs()
        if not await self._admitted():
            return 0
        queued = 0
        for program in await self.store.list_active_coaching_programs():
            try:
                user = await self.store.get_user_by_id(program["user_id"])
                if not user or not await self.store.has_coaching_consent(user["user_id"]):
                    continue
                history = await self.store.get_coaching_delivery_history(
                    user["user_id"], program["program_id"]
                )
                plan = plan_coaching_delivery(program, user, self.clock.utc_now(), history)
                if plan:
                    if not await self._admitted():
                        return queued
                    result = await self.store.enqueue_coaching_delivery(
                        user["user_id"],
                        program["program_id"],
                        program["version"],
                        **plan,
                    )
                    queued += result["status"] == "queued"
            except Exception:
                logger.warning("Coaching reconciliation failed for one Program")
        return queued

    async def drain_once(self, limit=25):
        if not await self._admitted():
            return 0
        sent = 0
        for row in await self.store.claim_coaching_deliveries(self.worker_id, limit):
            dispatched = False
            try:
                user_id, key, token = row["user_id"], row["delivery_key"], row["claim_token"]
                user = await self.store.get_user_by_id(user_id)
                program = await self.store.get_coaching_program(user_id, row["program_id"])
                history = await self.store.get_coaching_delivery_history(user_id, row["program_id"])
                prior = {
                    **history,
                    "deliveries": [
                        item for item in history["deliveries"] if item["delivery_key"] != key
                    ],
                }
                plan = (
                    plan_coaching_delivery(program, user, self.clock.utc_now(), prior)
                    if user and program
                    else None
                )
                if (
                    not plan
                    or plan["kind"] != row["kind"]
                    or not await self.store.has_coaching_consent(user_id)
                    or not reachable_here(self.channel, user)
                ):
                    await self.store.finish_coaching_delivery(user_id, key, token, "cancelled")
                    continue
                recipient = await proactive_recipient(self.channel, user)
                if recipient is None:
                    await self.store.finish_coaching_delivery(user_id, key, token, "cancelled")
                    continue
                auth_id = user.get("supabase_auth_id")
                activation = await self.store.get_activation_state(auth_id) if auth_id else {}
                if activation.get("completed") is not True:
                    await self.store.finish_coaching_delivery(user_id, key, token, "cancelled")
                    continue
                if not await self._admitted():
                    await self.store.finish_coaching_delivery(user_id, key, token, "cancelled")
                    continue
                if not await self.store.mark_coaching_dispatch(user_id, key, token):
                    continue
                dispatched = True  # From this durable boundary, crashes/timeouts never retry.
                if not await self._admitted():
                    await self.store.finish_coaching_delivery(user_id, key, token, "uncertain")
                    continue
                from src.conversations import ModeConversationService

                conversation = await ModeConversationService(self.store, self.channel).ensure(
                    user, "coach"
                )
                messages = {
                    "check_in": (
                        "Coach check-in: what progress would you like to report? "
                        "Pause or stop anytime."
                    ),
                    "follow_up": (
                        "A gentle Coach follow-up. No need to reply now; "
                        "I will wait for your return."
                    ),
                    "weekly_review": (
                        "Coach review: would you like to continue, adjust, pause or stop?"
                    ),
                }
                from src.coaching import coaching_callback

                actions = (
                    ("continue", "adjust", "pause", "stop")
                    if row["kind"] == "weekly_review"
                    else ("pause", "stop")
                )
                buttons = [
                    [
                        {
                            "text": action.capitalize(),
                            "callback_data": coaching_callback(
                                action, program["program_id"], program["version"]
                            ),
                        }
                        for action in actions
                    ]
                ]
                message_id = await self.channel.send_message(
                    recipient,
                    messages[row["kind"]],
                    conversation=conversation,
                    buttons=buttons,
                )
                outcome = "accepted" if message_id is not None else "rejected"
                await self.store.finish_coaching_delivery(user_id, key, token, outcome)
                sent += outcome == "accepted"
            except Exception:
                logger.warning("Coaching delivery failed for one occurrence")
                if isinstance(row, dict) and all(
                    name in row for name in ("user_id", "delivery_key", "claim_token")
                ):
                    try:
                        await self.store.finish_coaching_delivery(
                            row["user_id"], row["delivery_key"], row["claim_token"],
                            "uncertain" if dispatched else "cancelled",
                        )
                    except Exception:
                        logger.warning("Coaching delivery cleanup failed for one occurrence")
        return sent
