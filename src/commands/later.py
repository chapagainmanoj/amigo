"""Canonical cross-surface Later policy and command."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.commands.base import CommandContext
from src.utils import Clock, default_clock


@dataclass(frozen=True)
class LaterPlan:
    """Exact replacement Reminder intent produced by the policy."""

    step: int
    scheduled_at: datetime
    intended_local_date: date
    intended_local_time: time
    timezone: str
    quiet_hours_adjusted: bool
    task_due_date: date | None


def _parse_time(value: str | time | None) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    return time.fromisoformat(value)


def _in_quiet_hours(candidate: time, sleep: time, wake: time) -> bool:
    if sleep == wake:
        return False
    if sleep < wake:
        return sleep <= candidate < wake
    return candidate >= sleep or candidate < wake


class LaterPolicy:
    """Apply +60, +30, then next-planning-day wake-time semantics."""

    def __init__(self, clock: Clock = default_clock):
        self.clock = clock

    def plan(self, *, reminder: dict, task: dict, user: dict) -> LaterPlan:
        timezone = user.get("timezone") or "UTC"
        try:
            tz = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            raise ValueError("Invalid user timezone") from None

        local_now = self.clock.utc_now().replace(tzinfo=UTC).astimezone(tz)
        step = int(reminder.get("snooze_count", 0)) + 1
        wake = _parse_time(user["wake_time"] if "wake_time" in user else time(7, 30))
        sleep = _parse_time(user["sleep_time"] if "sleep_time" in user else time(23, 0))
        quiet_enabled = wake is not None and sleep is not None

        if step == 1:
            candidate = local_now + timedelta(minutes=60)
            task_due_date = None
        elif step == 2:
            candidate = local_now + timedelta(minutes=30)
            task_due_date = None
        else:
            planning_day = max(
                local_now.date(),
                date.fromisoformat(task["due_date"]) if task.get("due_date") else local_now.date(),
            ) + timedelta(days=1)
            candidate = datetime.combine(planning_day, wake or time(7, 30), tzinfo=tz)
            task_due_date = planning_day

        quiet_adjusted = False
        if quiet_enabled and _in_quiet_hours(candidate.timetz().replace(tzinfo=None), sleep, wake):
            quiet_adjusted = True
            wake_day = candidate.date()
            if sleep > wake and candidate.timetz().replace(tzinfo=None) >= sleep:
                wake_day += timedelta(days=1)
            candidate = datetime.combine(wake_day, wake, tzinfo=tz)
            if step >= 3:
                task_due_date = wake_day

        return LaterPlan(
            step=step,
            scheduled_at=candidate.astimezone(UTC),
            intended_local_date=candidate.date(),
            intended_local_time=candidate.timetz().replace(tzinfo=None),
            timezone=timezone,
            quiet_hours_adjusted=quiet_adjusted,
            task_due_date=task_due_date,
        )


class ApplyLaterCommand:
    """Acknowledge one Reminder and atomically create its policy replacement."""

    def __init__(self, store, policy: LaterPolicy | None = None):
        self.store = store
        self.policy = policy or LaterPolicy()

    async def run(
        self,
        context: CommandContext,
        *,
        reminder_id: str,
        expected_task_version: int | None = None,
    ) -> dict:
        if expected_task_version is not None and expected_task_version < 1:
            raise ValueError("Invalid Task version")
        if not context.idempotency_key.strip() or len(context.idempotency_key) > 200:
            raise ValueError("Invalid idempotency key")

        later_context = await self.store.get_later_context(
            reminder_id,
            context.actor_user_id,
        )
        if not later_context:
            raise ValueError("Reminder not found")
        plan = self.policy.plan(
            reminder=later_context["reminder"],
            task=later_context["task"],
            user=later_context["user"],
        )
        payload = {
            "command": "apply_later",
            "surface": context.surface,
            "reminder_id": reminder_id,
            "expected_task_version": expected_task_version,
        }
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        plan_input = asdict(plan)
        plan_input["scheduled_at"] = plan.scheduled_at.isoformat()
        plan_input["intended_local_date"] = plan.intended_local_date.isoformat()
        plan_input["intended_local_time"] = plan.intended_local_time.isoformat()
        plan_input["task_due_date"] = (
            plan.task_due_date.isoformat() if plan.task_due_date else None
        )
        return await self.store.apply_later_command(
            user_id=context.actor_user_id,
            idempotency_key=context.idempotency_key,
            payload_hash=payload_hash,
            reminder_id=reminder_id,
            expected_task_version=expected_task_version,
            **plan_input,
        )
