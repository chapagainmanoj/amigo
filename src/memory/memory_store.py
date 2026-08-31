"""In-memory implementation of MemoryStore — no database required.

Drop-in replacement for the Supabase-backed MemoryStore, designed for
local CLI development. All data lives in dicts and is lost on exit.
"""

import copy
import logging
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.commands.base import (
    IdempotencyConflictError,
    InvalidTransitionError,
    StaleVersionError,
)
from src.memory.later import apply_later_transition
from src.memory.pairing import (
    PAIRING_TOKEN_LIMIT,
    PAIRING_TOKEN_WINDOW,
    PairingTokenRateLimitError,
)
from src.memory.reminders import validate_reminder_updates
from src.memory.tasks import validate_task_status
from src.utils import local_day_utc_range, today_in_tz, utc_now, yesterday_in_tz

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return str(uuid.uuid4())


class InMemoryStore:
    """Dict-backed store implementing the same interface as MemoryStore."""

    def __init__(self):
        self._users: dict[str, dict] = {}          # user_id → profile
        self._sessions: dict[str, dict] = {}        # session_id → session
        self._messages: list[dict] = []
        self._tasks: dict[str, dict] = {}           # task_id → task
        self._reminders: dict[str, dict] = {}       # reminder_id → reminder
        self._feedback: list[dict] = []
        self._usage: list[dict] = []
        self._pairing_tokens: dict[str, dict] = {}
        self._command_receipts: dict[tuple[str, str], dict] = {}
        self._scheduler_outbox: dict[str, dict] = {}
        self._telegram_updates: dict[int, dict] = {}

    # ── User Profiles ──

    async def get_user_by_chat_id(self, chat_id: int) -> dict | None:
        for user in self._users.values():
            if user.get("telegram_chat_id") == chat_id:
                return dict(user)
        return None

    async def create_user(self, chat_id: int) -> dict:
        user_id = _new_id()
        user = {
            "user_id": user_id,
            "telegram_chat_id": chat_id,
            "name": None,
            "timezone": None,
            "wake_time": "07:30",
            "sleep_time": "23:00",
            "onboarding_step": 0,
            "onboarding_complete": False,
            "session_timeout_minutes": 120,
            "created_at": utc_now().isoformat(),
            "updated_at": utc_now().isoformat(),
        }
        self._users[user_id] = user
        return dict(user)

    async def update_user(self, user_id: str, updates: dict) -> dict:
        updates["updated_at"] = utc_now().isoformat()
        self._users[user_id].update(updates)
        return dict(self._users[user_id])

    # ── Telegram Update Claims ──

    async def claim_telegram_update(
        self, update_id: int, chat_id: int, update_kind: str
    ) -> dict:
        existing = self._telegram_updates.get(update_id)
        if existing:
            return {"claimed": False, **copy.deepcopy(existing)}
        row = {
            "update_id": update_id,
            "telegram_chat_id": chat_id,
            "update_kind": update_kind,
            "status": "processing",
            "failure_code": None,
            "claimed_at": utc_now().isoformat(),
            "finished_at": None,
        }
        self._telegram_updates[update_id] = row
        return {"claimed": True, **copy.deepcopy(row)}

    async def finish_telegram_update(
        self,
        update_id: int,
        *,
        status: str,
        failure_code: str | None = None,
    ) -> dict:
        if status not in {"completed", "failed"}:
            raise ValueError("Invalid Telegram update status")
        row = self._telegram_updates[update_id]
        if row["status"] != "processing":
            raise ValueError("Telegram update is already terminal")
        row.update(
            status=status,
            failure_code=failure_code,
            finished_at=utc_now().isoformat(),
        )
        return copy.deepcopy(row)

    # ── Sessions ──

    async def get_active_session(self, user_id: str) -> dict | None:
        active = [
            s for s in self._sessions.values()
            if s["user_id"] == user_id and s.get("ended_at") is None
        ]
        if not active:
            return None
        active.sort(key=lambda s: s["started_at"], reverse=True)
        return dict(active[0])

    async def create_session(self, user_id: str, session_type: str = "casual") -> dict:
        session_id = _new_id()
        now = utc_now().isoformat()
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "session_type": session_type,
            "started_at": now,
            "ended_at": None,
            "last_activity_at": now,
            "message_count": 0,
            "context_summary": None,
        }
        self._sessions[session_id] = session
        return dict(session)

    async def close_session(self, session_id: str, summary: str | None = None) -> None:
        if session_id in self._sessions:
            self._sessions[session_id]["ended_at"] = utc_now().isoformat()
            self._sessions[session_id]["context_summary"] = summary

    async def touch_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id]["last_activity_at"] = utc_now().isoformat()
            self._sessions[session_id]["message_count"] = (
                self._sessions[session_id].get("message_count", 0) + 1
            )

    # ── Messages ──

    async def add_message(
        self, session_id: str, user_id: str, role: str, content: str, channel: str = "cli"
    ) -> dict:
        msg = {
            "message_id": _new_id(),
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "channel": channel,
            "created_at": utc_now().isoformat(),
        }
        self._messages.append(msg)
        return dict(msg)

    async def get_session_messages(self, session_id: str) -> list[dict]:
        return [
            {"role": m["role"], "content": m["content"], "created_at": m["created_at"]}
            for m in self._messages
            if m["session_id"] == session_id
        ]

    async def has_session_on_local_day(self, user_id: str, timezone: str) -> bool:
        start_utc, end_utc = local_day_utc_range(timezone)
        for s in self._sessions.values():
            if s["user_id"] != user_id:
                continue
            started = datetime.fromisoformat(s["started_at"])
            if start_utc <= started < end_utc:
                return True
        return False

    async def get_yesterday_summary(self, user_id: str, timezone: str) -> str | None:
        yesterday = yesterday_in_tz(timezone)
        start_utc, end_utc = local_day_utc_range(timezone, yesterday)
        for s in sorted(
            self._sessions.values(),
            key=lambda x: x.get("ended_at") or "",
            reverse=True,
        ):
            if s["user_id"] != user_id:
                continue
            if s.get("context_summary") is None:
                continue
            started = datetime.fromisoformat(s["started_at"])
            if start_utc <= started < end_utc:
                return s["context_summary"]
        return None

    # ── Tasks ──

    async def create_task_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        title: str,
        category: str,
        due_date: str | None,
        session_id: str | None,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self._command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        if user_id not in self._users:
            raise ValueError("User not found")
        if session_id:
            session = self._sessions.get(session_id)
            if not session or session["user_id"] != user_id:
                raise ValueError("Session not found")

        task_id = _new_id()
        task = {
            "task_id": task_id,
            "user_id": user_id,
            "title": title,
            "category": category,
            "status": "pending",
            "due_date": due_date,
            "source_session_id": session_id,
            "created_date": today_in_tz("UTC").isoformat(),
            "created_at": utc_now().isoformat(),
            "suggested_time": None,
            "actual_completion": None,
            "deferred_count": 0,
            "version": 1,
        }
        self._tasks[task_id] = task
        result = {"task": copy.deepcopy(task)}
        self._command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def get_inbox_tasks(self, user_id: str) -> list[dict]:
        return [
            dict(task)
            for task in self._tasks.values()
            if task["user_id"] == user_id
            and task.get("due_date") is None
            and task["status"] == "pending"
        ]

    async def resolve_task_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        task_id: str,
        outcome: str,
        expected_version: int | None,
        acted_reminder_id: str | None,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self._command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        task = self._tasks.get(task_id)
        if not task or task["user_id"] != user_id:
            raise ValueError("Task not found")
        acted_reminder = None
        if acted_reminder_id:
            acted_reminder = self._reminders.get(acted_reminder_id)
            if (
                not acted_reminder
                or acted_reminder["user_id"] != user_id
                or acted_reminder["task_id"] != task_id
            ):
                raise ValueError("Reminder not found")
        if expected_version is not None and task.get("version", 1) != expected_version:
            raise StaleVersionError("Task version is stale")

        terminal = {"completed", "skipped", "cancelled"}
        transitioned = task["status"] == "pending"
        if task["status"] in terminal and task["status"] != outcome:
            raise InvalidTransitionError("Task is already resolved")

        effects = []
        changed_reminders = []
        if transitioned:
            task["status"] = outcome
            task["version"] = task.get("version", 1) + 1
            task["actual_completion"] = (
                utc_now().isoformat() if outcome == "completed" else None
            )
            active = {"pending", "sending", "sent"}
            for reminder in self._reminders.values():
                if (
                    reminder["task_id"] != task_id
                    or reminder["user_id"] != user_id
                    or reminder["status"] not in active
                ):
                    continue
                if (
                    reminder["reminder_id"] == acted_reminder_id
                    and reminder["status"] in {"sending", "sent"}
                ):
                    reminder["status"] = "acknowledged"
                else:
                    reminder["status"] = "cancelled"
                reminder["version"] = reminder.get("version", 1) + 1
                changed_reminders.append(copy.deepcopy(reminder))

                effect_key = f"cancel:{reminder['reminder_id']}"
                effect = self._scheduler_outbox.get(effect_key)
                if not effect:
                    effect = {
                        "effect_id": _new_id(),
                        "effect_key": effect_key,
                        "effect_type": "cancel",
                        "user_id": user_id,
                        "task_id": task_id,
                        "reminder_id": reminder["reminder_id"],
                        "payload": {},
                        "status": "pending",
                        "attempts": 0,
                        "worker_id": None,
                        "claimed_at": None,
                        "available_at": utc_now().isoformat(),
                        "completed_at": None,
                        "error_type": None,
                        "created_at": utc_now().isoformat(),
                    }
                    self._scheduler_outbox[effect_key] = effect
                effects.append(
                    {"effect_id": effect["effect_id"], "effect_type": "cancel"}
                )

        result = {
            "task": copy.deepcopy(task),
            "task_version": task.get("version", 1),
            "reminders": changed_reminders,
            "transitioned": transitioned,
            "effect_state": "queued" if effects else "none",
            "effects": effects,
        }
        self._command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def create_task(
        self,
        user_id: str,
        title: str,
        category: str = "other",
        session_id: str | None = None,
        suggested_time: str | None = None,
        timezone: str = "UTC",
    ) -> dict:
        task_id = _new_id()
        task = {
            "task_id": task_id,
            "user_id": user_id,
            "title": title,
            "category": category,
            "status": "pending",
            "due_date": today_in_tz(timezone).isoformat(),
            "source_session_id": session_id,
            "created_date": today_in_tz(timezone).isoformat(),
            "created_at": utc_now().isoformat(),
            "suggested_time": suggested_time,
            "actual_completion": None,
            "deferred_count": 0,
            "version": 1,
        }
        self._tasks[task_id] = task
        return dict(task)

    async def get_today_tasks(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        today = today_in_tz(timezone).isoformat()
        return [
            dict(t) for t in self._tasks.values()
            if t["user_id"] == user_id and t.get("due_date") == today
        ]

    async def get_yesterday_pending(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        yesterday = yesterday_in_tz(timezone).isoformat()
        return [
            dict(t) for t in self._tasks.values()
            if t["user_id"] == user_id
            and t["created_date"] == yesterday
            and t["status"] == "pending"
        ]

    async def update_task_status(self, task_id: str, status: str, user_id: str) -> dict:
        validate_task_status(status)
        task = self._tasks.get(task_id)
        if not task or task["user_id"] != user_id:
            raise ValueError("Task not found")
        task["status"] = status
        if status == "completed":
            task["actual_completion"] = utc_now().isoformat()
        return dict(task)

    # ── Reminders ──

    async def schedule_reminder_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        task_id: str | None,
        replace_reminder_id: str | None,
        scheduled_time: str,
        intended_local_date: str,
        intended_local_time: str,
        intended_timezone: str,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self._command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        if replace_reminder_id:
            replaced = self._reminders.get(replace_reminder_id)
            if not replaced or replaced["user_id"] != user_id:
                raise ValueError("Reminder not found")
            task_id = replaced["task_id"]
        if not task_id:
            raise ValueError("Task not found")
        task = self._tasks.get(task_id)
        if not task or task["user_id"] != user_id:
            raise ValueError("Task not found")

        user = self._users.get(user_id)
        if not user or not user.get("telegram_chat_id"):
            raise ValueError("User not found")

        effects = []
        active_statuses = {"pending", "sending", "sent"}
        for reminder in self._reminders.values():
            if reminder["task_id"] != task_id or reminder["status"] not in active_statuses:
                continue
            reminder["status"] = "cancelled"
            reminder["version"] = reminder.get("version", 1) + 1
            effect_key = f"cancel:{reminder['reminder_id']}"
            effect = self._scheduler_outbox.get(effect_key)
            if not effect:
                effect = {
                    "effect_id": _new_id(),
                    "effect_key": effect_key,
                    "effect_type": "cancel",
                    "user_id": user_id,
                    "task_id": task_id,
                    "reminder_id": reminder["reminder_id"],
                    "payload": {},
                    "status": "pending",
                    "attempts": 0,
                    "worker_id": None,
                    "claimed_at": None,
                    "available_at": utc_now().isoformat(),
                    "completed_at": None,
                    "created_at": utc_now().isoformat(),
                }
                self._scheduler_outbox[effect_key] = effect
            effects.append(copy.deepcopy(effect))

        reminder_id = _new_id()
        reminder = {
            "reminder_id": reminder_id,
            "task_id": task_id,
            "user_id": user_id,
            "scheduled_time": scheduled_time,
            "intended_local_date": intended_local_date,
            "intended_local_time": intended_local_time,
            "intended_timezone": intended_timezone,
            "status": "pending",
            "snooze_count": 0,
            "telegram_message_id": None,
            "follow_up_sent": False,
            "version": 1,
            "created_at": utc_now().isoformat(),
        }
        self._reminders[reminder_id] = reminder

        task["due_date"] = intended_local_date
        task["version"] = task.get("version", 1) + 1

        effect_key = f"schedule:{reminder_id}"
        schedule_effect = {
            "effect_id": _new_id(),
            "effect_key": effect_key,
            "effect_type": "schedule",
            "user_id": user_id,
            "task_id": task_id,
            "reminder_id": reminder_id,
            "payload": {
                "scheduled_time": scheduled_time,
                "telegram_chat_id": user["telegram_chat_id"],
                "task_title": task["title"],
            },
            "status": "pending",
            "attempts": 0,
            "worker_id": None,
            "claimed_at": None,
            "available_at": utc_now().isoformat(),
            "completed_at": None,
            "created_at": utc_now().isoformat(),
        }
        self._scheduler_outbox[effect_key] = schedule_effect
        effects.append(copy.deepcopy(schedule_effect))

        result = {
            "reminder": copy.deepcopy(reminder),
            "task_version": task["version"],
            "scheduled_time": scheduled_time,
            "effect_state": "queued",
            "effects": [
                {"effect_id": effect["effect_id"], "effect_type": effect["effect_type"]}
                for effect in effects
            ],
        }
        self._command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def cancel_reminder_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        reminder_id: str,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self._command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        reminder = self._reminders.get(reminder_id)
        if not reminder or reminder["user_id"] != user_id:
            raise ValueError("Reminder not found")
        task = self._tasks.get(reminder["task_id"])
        if not task or task["user_id"] != user_id:
            raise ValueError("Reminder not found")

        effect = None
        if reminder["status"] in {"pending", "sending", "sent"}:
            reminder["status"] = "cancelled"
            reminder["version"] = reminder.get("version", 1) + 1
            task["version"] = task.get("version", 1) + 1
            effect_key = f"cancel:{reminder_id}"
            effect = self._scheduler_outbox.get(effect_key)
            if not effect:
                effect = {
                    "effect_id": _new_id(),
                    "effect_key": effect_key,
                    "effect_type": "cancel",
                    "user_id": user_id,
                    "task_id": task["task_id"],
                    "reminder_id": reminder_id,
                    "payload": {},
                    "status": "pending",
                    "attempts": 0,
                    "worker_id": None,
                    "claimed_at": None,
                    "available_at": utc_now().isoformat(),
                    "completed_at": None,
                    "created_at": utc_now().isoformat(),
                }
                self._scheduler_outbox[effect_key] = effect

        result = {
            "reminder": copy.deepcopy(reminder),
            "task_version": task.get("version", 1),
            "effect_state": "queued" if effect else "none",
            "effects": (
                [{"effect_id": effect["effect_id"], "effect_type": "cancel"}]
                if effect
                else []
            ),
        }
        self._command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def claim_scheduler_effects(self, limit: int, worker_id: str) -> list[dict]:
        claimed = []
        now = utc_now()
        for effect in sorted(
            self._scheduler_outbox.values(), key=lambda item: item["created_at"]
        ):
            abandoned = (
                effect["status"] == "processing"
                and effect.get("claimed_at")
                and now - datetime.fromisoformat(effect["claimed_at"]) > timedelta(minutes=5)
            )
            available = datetime.fromisoformat(effect["available_at"]) <= now
            if (
                (effect["status"] != "pending" or not available)
                and not abandoned
            ) or len(claimed) >= limit:
                continue
            effect["status"] = "processing"
            effect["attempts"] += 1
            effect["worker_id"] = worker_id
            effect["claimed_at"] = now.isoformat()
            claimed.append(copy.deepcopy(effect))
        return claimed

    async def complete_scheduler_effect(
        self,
        effect_id: str,
        user_id: str,
        *,
        succeeded: bool,
        error_type: str | None,
    ) -> None:
        effect = next(
            (
                item
                for item in self._scheduler_outbox.values()
                if item["effect_id"] == effect_id and item["user_id"] == user_id
            ),
            None,
        )
        if not effect:
            raise ValueError("Scheduler effect not found")
        effect["status"] = (
            "completed" if succeeded else ("failed" if effect["attempts"] >= 5 else "pending")
        )
        effect["error_type"] = error_type
        effect["worker_id"] = None
        effect["claimed_at"] = None
        effect["completed_at"] = utc_now().isoformat() if succeeded else None
        effect["available_at"] = utc_now().isoformat()

    async def create_reminder(self, task_id: str, user_id: str, scheduled_time: str) -> dict:
        task = self._tasks.get(task_id)
        if not task or task["user_id"] != user_id:
            raise ValueError("Task not found")

        reminder_id = _new_id()
        reminder = {
            "reminder_id": reminder_id,
            "task_id": task_id,
            "user_id": user_id,
            "scheduled_time": scheduled_time,
            "status": "pending",
            "intended_local_date": None,
            "intended_local_time": None,
            "intended_timezone": None,
            "snooze_count": 0,
            "telegram_message_id": None,
            "version": 1,
        }
        self._reminders[reminder_id] = reminder
        return dict(reminder)

    async def update_reminder(self, reminder_id: str, updates: dict, user_id: str) -> dict:
        validate_reminder_updates(updates)
        reminder = self._reminders.get(reminder_id)
        if not reminder or reminder["user_id"] != user_id:
            raise ValueError("Reminder not found")
        reminder.update(updates)
        return dict(reminder)

    async def get_pending_reminders(self, user_id: str) -> list[dict]:
        results = []
        for r in self._reminders.values():
            if r["user_id"] == user_id and r["status"] == "pending":
                task = self._tasks.get(r["task_id"], {})
                entry = dict(r)
                entry["tasks"] = {
                    "title": task.get("title", ""),
                    "category": task.get("category", ""),
                }
                results.append(entry)
        results.sort(key=lambda x: x["scheduled_time"])
        return results

    async def get_reminder_with_task(self, reminder_id: str, user_id: str) -> dict | None:
        r = self._reminders.get(reminder_id)
        if not r or r["user_id"] != user_id:
            return None
        task = self._tasks.get(r["task_id"], {})
        entry = dict(r)
        entry["tasks"] = {"title": task.get("title", ""), "category": task.get("category", "")}
        return entry

    async def get_later_context(self, reminder_id: str, user_id: str) -> dict | None:
        reminder = self._reminders.get(reminder_id)
        task = self._tasks.get(reminder["task_id"]) if reminder else None
        user = self._users.get(user_id)
        if (
            not reminder
            or reminder["user_id"] != user_id
            or not task
            or task["user_id"] != user_id
            or not user
        ):
            return None
        return {
            "reminder": copy.deepcopy(reminder),
            "task": copy.deepcopy(task),
            "user": copy.deepcopy(user),
        }

    async def apply_later_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        reminder_id: str,
        expected_task_version: int | None,
        step: int,
        scheduled_at: str,
        intended_local_date: str,
        intended_local_time: str,
        timezone: str,
        quiet_hours_adjusted: bool,
        task_due_date: str | None,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self._command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        reminder = self._reminders.get(reminder_id)
        task = self._tasks.get(reminder["task_id"]) if reminder else None
        user = self._users.get(user_id)
        if (
            not reminder
            or reminder["user_id"] != user_id
            or not task
            or task["user_id"] != user_id
            or not user
        ):
            raise ValueError("Reminder not found")
        if reminder["status"] not in {"pending", "sending", "sent"}:
            raise ValueError("Reminder not active")
        if task["status"] != "pending":
            raise ValueError("Task not pending")
        if expected_task_version is not None and task.get("version", 1) != expected_task_version:
            raise StaleVersionError("Task version is stale")
        if step != int(reminder.get("snooze_count", 0)) + 1:
            raise ValueError("Later step is stale")

        result = apply_later_transition(
            user=user,
            task=task,
            reminder=reminder,
            outbox=self._scheduler_outbox,
            new_id=_new_id,
            step=step,
            scheduled_at=scheduled_at,
            intended_local_date=intended_local_date,
            intended_local_time=intended_local_time,
            timezone=timezone,
            quiet_hours_adjusted=quiet_hours_adjusted,
            task_due_date=task_due_date,
        )
        self._reminders[result["reminder"]["reminder_id"]] = result["reminder"]
        self._command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return copy.deepcopy(result)

    async def claim_reminder_for_send(self, reminder_id: str, user_id: str) -> dict | None:
        r = self._reminders.get(reminder_id)
        if not r or r["user_id"] != user_id or r["status"] != "pending":
            return None
        r["status"] = "sending"
        task = self._tasks.get(r["task_id"], {})
        return {
            "status": r["status"],
            "tasks": {"status": task.get("status", "pending")},
        }

    async def get_pending_reminders_for_reload(self, cutoff: datetime) -> list[dict]:
        results = []
        for r in self._reminders.values():
            if r["status"] != "pending":
                continue
            scheduled = datetime.fromisoformat(r["scheduled_time"])
            if scheduled.tzinfo is not None:
                from zoneinfo import ZoneInfo
                scheduled = scheduled.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            if scheduled >= cutoff:
                task = self._tasks.get(r["task_id"], {})
                user = self._users.get(r["user_id"], {})
                entry = dict(r)
                entry["tasks"] = {"title": task.get("title", "")}
                entry["user_profiles"] = {"telegram_chat_id": user.get("telegram_chat_id")}
                results.append(entry)
        return results

    async def acknowledge_reminders_for_task(self, task_id: str, user_id: str) -> list[str]:
        ids = []
        for r in self._reminders.values():
            if r["task_id"] == task_id and r["user_id"] == user_id and r["status"] == "pending":
                r["status"] = "acknowledged"
                ids.append(r["reminder_id"])
        return ids

    # ── Feedback ──

    async def save_feedback(
        self, user_id: str, content: str, session_id: str | None = None,
    ) -> dict:
        entry = {
            "feedback_id": _new_id(),
            "user_id": user_id,
            "content": content,
            "session_id": session_id,
            "created_at": utc_now().isoformat(),
        }
        self._feedback.append(entry)
        return entry

    # ── Usage Events ──

    async def log_usage(
        self, user_id: str, model: str, input_tokens: int,
        output_tokens: int, session_id: str | None = None,
    ) -> None:
        self._usage.append({
            "user_id": user_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "session_id": session_id,
        })

    # ── Pairing and Account Linking ──

    async def get_user_by_auth_id(self, auth_id: str) -> dict | None:
        """Find user profile linked to a Supabase auth.uid()."""
        for user in self._users.values():
            if user.get("supabase_auth_id") == auth_id:
                return dict(user)
        return None

    async def get_dashboard_snapshot(self, user_id: str) -> dict:
        from src.dashboard_snapshot import build_dashboard_snapshot

        user = self._users.get(user_id)
        if not user:
            raise ValueError("User not found")
        return build_dashboard_snapshot(
            user,
            [item for item in self._tasks.values() if item["user_id"] == user_id],
            [item for item in self._reminders.values() if item["user_id"] == user_id],
            [item for item in self._sessions.values() if item["user_id"] == user_id],
        )

    async def create_pairing_token(self, token: str, auth_id: str, expires_at: datetime) -> dict:
        """Create a new pairing token linked to a Supabase auth.uid()."""
        now = utc_now()
        window_start = now - PAIRING_TOKEN_WINDOW
        recent_count = sum(
            1
            for row in self._pairing_tokens.values()
            if row["supabase_auth_id"] == auth_id
            and datetime.fromisoformat(row["created_at"]) >= window_start
        )
        if recent_count >= PAIRING_TOKEN_LIMIT:
            raise PairingTokenRateLimitError

        for existing in self._pairing_tokens.values():
            if existing["supabase_auth_id"] == auth_id and not existing["consumed"]:
                existing["invalidated_at"] = now.isoformat()

        row = {
            "token": token,
            "supabase_auth_id": auth_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "consumed": False,
            "invalidated_at": None,
        }
        self._pairing_tokens[token] = row
        return dict(row)

    async def complete_pairing(self, token: str, chat_id: int) -> dict:
        """Atomically consume a token and link identities without reassignment."""
        row = self._pairing_tokens.get(token)
        if not row or row["consumed"] or row.get("invalidated_at"):
            return {"status": "invalid_token"}

        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        if expires_at < utc_now():
            return {"status": "invalid_token"}

        auth_id = row["supabase_auth_id"]
        chat_user = await self.get_user_by_chat_id(chat_id)
        auth_user = await self.get_user_by_auth_id(auth_id)
        if chat_user and auth_user and chat_user["user_id"] == auth_user["user_id"]:
            row["consumed"] = True
            return {"status": "already_paired"}
        if (chat_user and chat_user.get("supabase_auth_id") not in (None, auth_id)) or (
            auth_user and auth_user.get("telegram_chat_id") != chat_id
        ):
            return {"status": "conflict"}

        user = chat_user or await self.create_user(chat_id)
        await self.update_user(user["user_id"], {"supabase_auth_id": auth_id})
        row["consumed"] = True
        return {"status": "paired"}
