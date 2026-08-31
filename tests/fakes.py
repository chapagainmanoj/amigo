"""Shared fakes for testing — no real Supabase, Telegram, or Gemini needed.

These fakes implement the same interfaces as production classes but store
everything in-memory dictionaries. They're intentionally simple — just enough
to test behavior, not to replicate Supabase query semantics.
"""

from __future__ import annotations

import copy
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
from src.utils import utc_now


class FakeChannel:
    """In-memory message channel. Records all sent messages for assertions."""

    def __init__(self):
        self.sent: list[dict] = []  # [{chat_id, text, buttons}]
        self.edited: list[dict] = []

    async def send_message(
        self, chat_id: str | int, text: str, *, buttons=None
    ) -> int | None:
        msg_id = len(self.sent) + 1
        self.sent.append({
            "chat_id": chat_id,
            "text": text,
            "buttons": buttons,
            "message_id": msg_id,
        })
        return msg_id

    async def edit_message_buttons(self, chat_id, message_id, *, buttons=None):
        self.edited.append({"chat_id": chat_id, "message_id": message_id, "buttons": buttons})

    @property
    def last_text(self) -> str:
        return self.sent[-1]["text"] if self.sent else ""

    @property
    def texts(self) -> list[str]:
        return [m["text"] for m in self.sent]


class FakeStore:
    """In-memory store. Mimics MemoryStore's async interface with dicts."""

    def __init__(self):
        self.users: dict[int, dict] = {}  # chat_id -> user
        self.sessions: list[dict] = []
        self.messages: list[dict] = []
        self.tasks: list[dict] = []
        self.reminders: list[dict] = []
        self.feedback: list[dict] = []
        self.usage: list[dict] = []
        self.pairing_tokens: dict[str, dict] = {}
        self.command_receipts: dict[tuple[str, str], dict] = {}
        self.scheduler_outbox: dict[str, dict] = {}
        self.telegram_updates: dict[int, dict] = {}
        # Fake Supabase client for direct queries (used by SessionManager)
        self.db = FakeDB(self)

    async def get_user_by_chat_id(self, chat_id: int) -> dict | None:
        return self.users.get(chat_id)

    async def create_user(self, chat_id: int) -> dict:
        user = {
            "user_id": str(uuid.uuid4()),
            "telegram_chat_id": chat_id,
            "name": None,
            "timezone": None,
            "onboarding_step": 0,
            "onboarding_complete": False,
            "wake_time": "07:30",
            "sleep_time": "23:00",
            "session_timeout_minutes": 120,
            "updated_at": utc_now().isoformat(),
        }
        self.users[chat_id] = user
        return user

    async def update_user(self, user_id: str, updates: dict) -> dict:
        for _chat_id, user in self.users.items():
            if user["user_id"] == user_id:
                user.update(updates)
                return user
        raise ValueError(f"User {user_id} not found")

    async def claim_telegram_update(self, update_id, chat_id, update_kind):
        existing = self.telegram_updates.get(update_id)
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
        self.telegram_updates[update_id] = row
        return {"claimed": True, **copy.deepcopy(row)}

    async def finish_telegram_update(
        self, update_id, *, status, failure_code=None
    ):
        if status not in {"completed", "failed"}:
            raise ValueError("Invalid Telegram update status")
        row = self.telegram_updates[update_id]
        if row["status"] != "processing":
            raise ValueError("Telegram update is already terminal")
        row.update(
            status=status,
            failure_code=failure_code,
            finished_at=utc_now().isoformat(),
        )
        return copy.deepcopy(row)

    async def get_active_session(self, user_id: str) -> dict | None:
        for s in reversed(self.sessions):
            if s["user_id"] == user_id and s.get("ended_at") is None:
                return s
        return None

    async def create_session(self, user_id: str, session_type: str = "casual") -> dict:
        session = {
            "session_id": str(uuid.uuid4()),
            "user_id": user_id,
            "session_type": session_type,
            "started_at": utc_now().isoformat(),
            "last_activity_at": utc_now().isoformat(),
            "ended_at": None,
            "message_count": 0,
            "context_summary": None,
        }
        self.sessions.append(session)
        return session

    async def close_session(self, session_id: str, summary: str | None = None) -> None:
        for s in self.sessions:
            if s["session_id"] == session_id:
                s["ended_at"] = utc_now().isoformat()
                s["context_summary"] = summary

    async def touch_session(self, session_id: str) -> None:
        for s in self.sessions:
            if s["session_id"] == session_id:
                s["last_activity_at"] = utc_now().isoformat()
                s["message_count"] = (s.get("message_count") or 0) + 1

    async def add_message(self, session_id, user_id, role, content, channel="telegram"):
        msg = {
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "channel": channel,
            "created_at": utc_now().isoformat(),
        }
        self.messages.append(msg)
        return msg

    async def get_session_messages(self, session_id: str) -> list[dict]:
        return [m for m in self.messages if m["session_id"] == session_id]

    async def has_session_on_local_day(self, user_id: str, timezone: str) -> bool:
        from src.utils import local_day_utc_range
        start_utc, end_utc = local_day_utc_range(timezone)
        for session in self.sessions:
            if session["user_id"] != user_id:
                continue
            started_at = datetime.fromisoformat(session["started_at"])
            if start_utc <= started_at < end_utc:
                return True
        return False

    async def get_yesterday_summary(self, user_id: str, timezone: str) -> str | None:
        from src.utils import local_day_utc_range, yesterday_in_tz
        start_utc, end_utc = local_day_utc_range(timezone, yesterday_in_tz(timezone))
        candidates = []
        for session in self.sessions:
            if session["user_id"] != user_id or not session.get("context_summary"):
                continue
            started_at = datetime.fromisoformat(session["started_at"])
            if start_utc <= started_at < end_utc:
                candidates.append(session)
        if not candidates:
            return None
        candidates.sort(key=lambda s: s.get("ended_at") or "", reverse=True)
        return candidates[0]["context_summary"]

    async def create_task(self, user_id, title, category="other",
                          session_id=None, suggested_time=None, timezone="UTC"):
        from src.utils import today_in_tz
        today = today_in_tz(timezone).isoformat()
        # Deduplication — mirror MemoryStore behaviour
        for t in self.tasks:
            if (
                t["user_id"] == user_id
                and t["title"] == title
                and t["created_date"] == today
                and t["status"] not in ("completed", "skipped", "cancelled")
            ):
                return t
        task = {
            "task_id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": title,
            "category": category,
            "status": "pending",
            "due_date": today,
            "created_date": today,
            "source_session_id": session_id,
            "suggested_time": suggested_time,
            "deferred_count": 0,
            "actual_completion": None,
            "created_at": utc_now().isoformat(),
            "version": 1,
        }
        self.tasks.append(task)
        return task

    async def get_today_tasks(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        from src.utils import today_in_tz
        today = today_in_tz(timezone).isoformat()
        return [t for t in self.tasks if t["user_id"] == user_id and t.get("due_date") == today]

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
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        if not any(user["user_id"] == user_id for user in self.users.values()):
            raise ValueError("User not found")
        if session_id:
            session = next(
                (item for item in self.sessions if item["session_id"] == session_id),
                None,
            )
            if not session or session["user_id"] != user_id:
                raise ValueError("Session not found")

        task = {
            "task_id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": title,
            "category": category,
            "status": "pending",
            "due_date": due_date,
            "created_date": utc_now().date().isoformat(),
            "source_session_id": session_id,
            "suggested_time": None,
            "deferred_count": 0,
            "actual_completion": None,
            "created_at": utc_now().isoformat(),
            "version": 1,
        }
        self.tasks.append(task)
        result = {"task": copy.deepcopy(task)}
        self.command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def get_inbox_tasks(self, user_id: str) -> list[dict]:
        return [
            task
            for task in self.tasks
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
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        task = next(
            (
                item
                for item in self.tasks
                if item["task_id"] == task_id and item["user_id"] == user_id
            ),
            None,
        )
        if not task:
            raise ValueError("Task not found")
        if acted_reminder_id and not any(
            reminder["reminder_id"] == acted_reminder_id
            and reminder["user_id"] == user_id
            and reminder["task_id"] == task_id
            for reminder in self.reminders
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
            for reminder in self.reminders:
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
                effect = self.scheduler_outbox.get(effect_key)
                if not effect:
                    effect = {
                        "effect_id": str(uuid.uuid4()),
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
                    self.scheduler_outbox[effect_key] = effect
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
        self.command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def get_yesterday_pending(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        from src.utils import yesterday_in_tz
        yesterday = yesterday_in_tz(timezone).isoformat()
        return [
            t for t in self.tasks
            if t["user_id"] == user_id
            and t["created_date"] == yesterday
            and t["status"] == "pending"
        ]

    async def update_task_status(self, task_id: str, status: str, user_id: str) -> dict:
        validate_task_status(status)
        for t in self.tasks:
            if t["task_id"] == task_id and t["user_id"] == user_id:
                t["status"] = status
                if status == "completed":
                    t["actual_completion"] = utc_now().isoformat()
                return t
        raise ValueError("Task not found")

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
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        if replace_reminder_id:
            replaced = next(
                (
                    reminder
                    for reminder in self.reminders
                    if reminder["reminder_id"] == replace_reminder_id
                    and reminder["user_id"] == user_id
                ),
                None,
            )
            if not replaced:
                raise ValueError("Reminder not found")
            task_id = replaced["task_id"]
        task = next(
            (
                item
                for item in self.tasks
                if item["task_id"] == task_id and item["user_id"] == user_id
            ),
            None,
        )
        if not task:
            raise ValueError("Task not found")
        user = next(
            (item for item in self.users.values() if item["user_id"] == user_id),
            None,
        )
        if not user or not user.get("telegram_chat_id"):
            raise ValueError("User not found")

        effects = []
        for reminder in self.reminders:
            if reminder["task_id"] != task_id or reminder["status"] not in {
                "pending",
                "sending",
                "sent",
            }:
                continue
            reminder["status"] = "cancelled"
            reminder["version"] = reminder.get("version", 1) + 1
            effect_key = f"cancel:{reminder['reminder_id']}"
            effect = self.scheduler_outbox.get(effect_key)
            if not effect:
                effect = {
                    "effect_id": str(uuid.uuid4()),
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
                self.scheduler_outbox[effect_key] = effect
            effects.append(copy.deepcopy(effect))

        reminder_id = str(uuid.uuid4())
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
        self.reminders.append(reminder)
        task["due_date"] = intended_local_date
        task["version"] = task.get("version", 1) + 1

        effect_key = f"schedule:{reminder_id}"
        schedule_effect = {
            "effect_id": str(uuid.uuid4()),
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
        self.scheduler_outbox[effect_key] = schedule_effect
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
        self.command_receipts[receipt_key] = {
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
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        reminder = next(
            (
                item
                for item in self.reminders
                if item["reminder_id"] == reminder_id and item["user_id"] == user_id
            ),
            None,
        )
        if not reminder:
            raise ValueError("Reminder not found")
        task = next(
            (
                item
                for item in self.tasks
                if item["task_id"] == reminder["task_id"] and item["user_id"] == user_id
            ),
            None,
        )
        if not task:
            raise ValueError("Reminder not found")

        effect = None
        if reminder["status"] in {"pending", "sending", "sent"}:
            reminder["status"] = "cancelled"
            reminder["version"] = reminder.get("version", 1) + 1
            task["version"] = task.get("version", 1) + 1
            effect_key = f"cancel:{reminder_id}"
            effect = self.scheduler_outbox.get(effect_key)
            if not effect:
                effect = {
                    "effect_id": str(uuid.uuid4()),
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
                self.scheduler_outbox[effect_key] = effect

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
        self.command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def claim_scheduler_effects(self, limit: int, worker_id: str) -> list[dict]:
        claimed = []
        now = utc_now()
        for effect in sorted(
            self.scheduler_outbox.values(), key=lambda item: item["created_at"]
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
                for item in self.scheduler_outbox.values()
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

    async def create_reminder(self, task_id, user_id, scheduled_time):
        task = next(
            (t for t in self.tasks if t["task_id"] == task_id and t["user_id"] == user_id),
            None,
        )
        if not task:
            raise ValueError("Task not found")

        reminder = {
            "reminder_id": str(uuid.uuid4()),
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
        self.reminders.append(reminder)
        return reminder

    async def update_reminder(self, reminder_id: str, updates: dict, user_id: str) -> dict:
        validate_reminder_updates(updates)
        for r in self.reminders:
            if r["reminder_id"] == reminder_id and r["user_id"] == user_id:
                r.update(updates)
                return r
        raise ValueError("Reminder not found")

    async def get_pending_reminders(self, user_id: str) -> list[dict]:
        return [
            r for r in self.reminders
            if r["user_id"] == user_id and r["status"] == "pending"
        ]

    async def get_reminder_with_task(self, reminder_id: str, user_id: str) -> dict | None:
        for reminder in self.reminders:
            if reminder["reminder_id"] != reminder_id or reminder["user_id"] != user_id:
                continue
            task = next((t for t in self.tasks if t["task_id"] == reminder["task_id"]), None)
            if not task:
                return {**reminder, "tasks": {"title": "your task", "category": "other"}}
            return {**reminder, "tasks": {"title": task["title"], "category": task["category"]}}
        return None

    async def get_later_context(self, reminder_id: str, user_id: str) -> dict | None:
        reminder = next(
            (
                item
                for item in self.reminders
                if item["reminder_id"] == reminder_id and item["user_id"] == user_id
            ),
            None,
        )
        task = next(
            (
                item
                for item in self.tasks
                if reminder
                and item["task_id"] == reminder["task_id"]
                and item["user_id"] == user_id
            ),
            None,
        )
        user = next(
            (item for item in self.users.values() if item["user_id"] == user_id),
            None,
        )
        if not reminder or not task or not user:
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
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        reminder = next(
            (
                item
                for item in self.reminders
                if item["reminder_id"] == reminder_id and item["user_id"] == user_id
            ),
            None,
        )
        task = next(
            (
                item
                for item in self.tasks
                if reminder
                and item["task_id"] == reminder["task_id"]
                and item["user_id"] == user_id
            ),
            None,
        )
        user = next(
            (item for item in self.users.values() if item["user_id"] == user_id),
            None,
        )
        if not reminder or not task or not user:
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
            outbox=self.scheduler_outbox,
            new_id=lambda: str(uuid.uuid4()),
            step=step,
            scheduled_at=scheduled_at,
            intended_local_date=intended_local_date,
            intended_local_time=intended_local_time,
            timezone=timezone,
            quiet_hours_adjusted=quiet_hours_adjusted,
            task_due_date=task_due_date,
        )
        self.reminders.append(result["reminder"])
        self.command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return copy.deepcopy(result)

    async def claim_reminder_for_send(self, reminder_id: str, user_id: str) -> dict | None:
        for reminder in self.reminders:
            if (
                reminder["reminder_id"] != reminder_id
                or reminder["user_id"] != user_id
                or reminder["status"] != "pending"
            ):
                continue
            reminder["status"] = "sending"
            task = next((t for t in self.tasks if t["task_id"] == reminder["task_id"]), None)
            return {
                "status": reminder["status"],
                "tasks": {"status": task["status"] if task else None},
            }
        return None

    async def get_pending_reminders_for_reload(self, cutoff: datetime) -> list[dict]:
        rows = []
        for reminder in self.reminders:
            scheduled = datetime.fromisoformat(reminder["scheduled_time"])
            if reminder["status"] != "pending" or scheduled < cutoff:
                continue
            task = next((t for t in self.tasks if t["task_id"] == reminder["task_id"]), None)
            user = next(
                (u for u in self.users.values() if u["user_id"] == reminder["user_id"]),
                None,
            )
            rows.append({
                **reminder,
                "tasks": {"title": task["title"] if task else "your task"},
                "user_profiles": {
                    "telegram_chat_id": user["telegram_chat_id"] if user else None
                },
            })
        return rows

    async def acknowledge_reminders_for_task(self, task_id: str, user_id: str) -> list[str]:
        ids = []
        for r in self.reminders:
            if r["task_id"] == task_id and r["user_id"] == user_id and r["status"] == "pending":
                r["status"] = "acknowledged"
                ids.append(r["reminder_id"])
        return ids

    async def save_feedback(self, user_id, content, session_id=None):
        fb = {"user_id": user_id, "content": content, "session_id": session_id}
        self.feedback.append(fb)
        return fb

    async def log_usage(self, user_id, model, input_tokens, output_tokens, session_id=None):
        self.usage.append({
            "user_id": user_id, "model": model,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
        })

    # ── Pairing and Account Linking ──

    async def get_user_by_auth_id(self, auth_id: str) -> dict | None:
        """Find user profile linked to a Supabase auth.uid()."""
        for user in self.users.values():
            if user.get("supabase_auth_id") == auth_id:
                return dict(user)
        return None

    async def get_dashboard_snapshot(self, user_id: str) -> dict:
        from src.dashboard_snapshot import build_dashboard_snapshot

        user = next((item for item in self.users.values() if item["user_id"] == user_id), None)
        if not user:
            raise ValueError("User not found")
        return build_dashboard_snapshot(
            user,
            [item for item in self.tasks if item["user_id"] == user_id],
            [item for item in self.reminders if item["user_id"] == user_id],
            [item for item in self.sessions if item["user_id"] == user_id],
        )

    async def create_pairing_token(self, token: str, auth_id: str, expires_at: datetime) -> dict:
        """Create a new pairing token linked to a Supabase auth.uid()."""
        now = utc_now()
        window_start = now - PAIRING_TOKEN_WINDOW
        recent_count = sum(
            1
            for row in self.pairing_tokens.values()
            if row["supabase_auth_id"] == auth_id
            and datetime.fromisoformat(row["created_at"]) >= window_start
        )
        if recent_count >= PAIRING_TOKEN_LIMIT:
            raise PairingTokenRateLimitError

        for existing in self.pairing_tokens.values():
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
        self.pairing_tokens[token] = row
        return dict(row)

    async def complete_pairing(self, token: str, chat_id: int) -> dict:
        """Atomically consume a token and link identities without reassignment."""
        row = self.pairing_tokens.get(token)
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



class FakeDB:
    """Minimal fake for self.store.db.table(...) chains used by SessionManager."""

    def __init__(self, store: FakeStore):
        self._store = store

    def table(self, name: str):
        return FakeTable(self._store, name)


class FakeTable:
    """Chainable fake for Supabase table queries."""

    def __init__(self, store: FakeStore, table_name: str):
        self._store = store
        self._table = table_name
        self._filters: dict = {}
        self._select_cols = "*"
        self._limit_n = None

    def select(self, cols):
        self._select_cols = cols
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def gte(self, col, val):
        self._filters[f"{col}__gte"] = val
        return self

    def lt(self, col, val):
        self._filters[f"{col}__lt"] = val
        return self

    def is_(self, col, val):
        self._filters[f"{col}__is"] = val
        return self

    def in_(self, col, vals):
        self._filters[f"{col}__in"] = vals
        return self

    def not_(self):
        return self

    def order(self, col, desc=False):
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def maybe_single(self):
        return self

    def single(self):
        return self

    def execute(self):
        """Return matching rows from the in-memory store."""
        if self._table == "sessions":
            data = self._filter_list(self._store.sessions)
        elif self._table == "tasks":
            data = self._filter_list(self._store.tasks)
        elif self._table == "reminders":
            data = self._filter_list(self._store.reminders)
        else:
            data = []

        if self._limit_n:
            data = data[:self._limit_n]

        return FakeResult(data)

    def update(self, updates):
        return self

    def insert(self, data):
        return self

    def _filter_list(self, items: list[dict]) -> list[dict]:
        result = []
        for item in items:
            match = True
            for key, val in self._filters.items():
                if "__gte" in key:
                    col = key.replace("__gte", "")
                    if item.get(col, "") < val:
                        match = False
                elif "__lt" in key:
                    col = key.replace("__lt", "")
                    if item.get(col, "") >= val:
                        match = False
                elif "__is" in key:
                    col = key.replace("__is", "")
                    if val == "null" and item.get(col) is not None:
                        match = False
                elif "__in" in key:
                    col = key.replace("__in", "")
                    if item.get(col) not in val:
                        match = False
                else:
                    if item.get(key) != val:
                        match = False
            if match:
                result.append(item)
        return result


class FakeResult:
    def __init__(self, data):
        if isinstance(data, list) and len(data) == 0:
            self.data = []
        elif isinstance(data, list):
            self.data = data
        else:
            self.data = data



class FakeScheduler:
    """Fake reminder scheduler. Records schedule/cancel calls."""

    def __init__(self):
        self.scheduled: list[dict] = []
        self.cancelled: list[str] = []

    def schedule_reminder(self, user_id, reminder_id, send_time, chat_id, task_title):
        self.scheduled.append({
            "user_id": user_id, "reminder_id": reminder_id,
            "send_time": send_time, "chat_id": chat_id, "task_title": task_title,
        })

    def cancel_reminder(self, user_id, reminder_id):
        self.cancelled.append(reminder_id)
