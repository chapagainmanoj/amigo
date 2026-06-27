"""In-memory implementation of MemoryStore — no database required.

Drop-in replacement for the Supabase-backed MemoryStore, designed for
local CLI development. All data lives in dicts and is lost on exit.
"""

import logging
import uuid
from datetime import datetime

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
            "source_session_id": session_id,
            "created_date": today_in_tz(timezone).isoformat(),
            "created_at": utc_now().isoformat(),
            "suggested_time": suggested_time,
            "actual_completion": None,
            "deferred_count": 0,
        }
        self._tasks[task_id] = task
        return dict(task)

    async def get_today_tasks(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        today = today_in_tz(timezone).isoformat()
        return [
            dict(t) for t in self._tasks.values()
            if t["user_id"] == user_id and t["created_date"] == today
        ]

    async def get_yesterday_pending(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        yesterday = yesterday_in_tz(timezone).isoformat()
        return [
            dict(t) for t in self._tasks.values()
            if t["user_id"] == user_id
            and t["created_date"] == yesterday
            and t["status"] in ("pending", "deferred")
        ]

    async def update_task_status(self, task_id: str, status: str) -> dict:
        task = self._tasks[task_id]
        task["status"] = status
        if status == "done":
            task["actual_completion"] = utc_now().isoformat()
        if status == "deferred":
            task["deferred_count"] = (task.get("deferred_count") or 0) + 1
        return dict(task)

    # ── Reminders ──

    async def create_reminder(self, task_id: str, user_id: str, scheduled_time: str) -> dict:
        reminder_id = _new_id()
        reminder = {
            "reminder_id": reminder_id,
            "task_id": task_id,
            "user_id": user_id,
            "scheduled_time": scheduled_time,
            "status": "pending",
            "snooze_count": 0,
            "telegram_message_id": None,
        }
        self._reminders[reminder_id] = reminder
        return dict(reminder)

    async def update_reminder(self, reminder_id: str, updates: dict) -> dict:
        self._reminders[reminder_id].update(updates)
        return dict(self._reminders[reminder_id])

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

    async def get_reminder_with_task(self, reminder_id: str) -> dict | None:
        r = self._reminders.get(reminder_id)
        if not r:
            return None
        task = self._tasks.get(r["task_id"], {})
        entry = dict(r)
        entry["tasks"] = {"title": task.get("title", ""), "category": task.get("category", "")}
        return entry

    async def get_reminder_for_send(self, reminder_id: str) -> dict | None:
        r = self._reminders.get(reminder_id)
        if not r:
            return None
        task = self._tasks.get(r["task_id"], {})
        return {
            "status": r["status"],
            "tasks": {"status": task.get("status", "pending")},
        }

    async def claim_reminder_for_send(self, reminder_id: str) -> dict | None:
        r = self._reminders.get(reminder_id)
        if not r or r["status"] != "pending":
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

    async def create_pairing_token(self, token: str, auth_id: str, expires_at: datetime) -> dict:
        """Create a new pairing token linked to a Supabase auth.uid()."""
        row = {
            "token": token,
            "supabase_auth_id": auth_id,
            "expires_at": expires_at.isoformat(),
            "consumed": False,
        }
        self._pairing_tokens[token] = row
        return dict(row)

    async def consume_pairing_token(self, token: str) -> dict | None:
        """Atomically claim/consume a pairing token if valid and not expired.

        Returns token dict if consumed successfully, otherwise None.
        """
        row = self._pairing_tokens.get(token)
        if not row:
            return None
        if row["consumed"]:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is not None:
            # make timezone naive for comparison if needed
            from zoneinfo import ZoneInfo
            expires_at = expires_at.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        if expires_at < utc_now().replace(tzinfo=None):
            return None
        row["consumed"] = True
        return dict(row)

