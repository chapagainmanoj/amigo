"""Shared fakes for testing — no real Supabase, Telegram, or Gemini needed.

These fakes implement the same interfaces as production classes but store
everything in-memory dictionaries. They're intentionally simple — just enough
to test behavior, not to replicate Supabase query semantics.
"""

from __future__ import annotations

import uuid
from datetime import datetime

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
                and t["status"] not in ("done", "skipped")
            ):
                return t
        task = {
            "task_id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": title,
            "category": category,
            "status": "pending",
            "created_date": today,
            "source_session_id": session_id,
            "suggested_time": suggested_time,
            "deferred_count": 0,
            "actual_completion": None,
            "created_at": utc_now().isoformat(),
        }
        self.tasks.append(task)
        return task

    async def get_today_tasks(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        from src.utils import today_in_tz
        today = today_in_tz(timezone).isoformat()
        return [t for t in self.tasks if t["user_id"] == user_id and t["created_date"] == today]

    async def get_yesterday_pending(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        from src.utils import yesterday_in_tz
        yesterday = yesterday_in_tz(timezone).isoformat()
        return [
            t for t in self.tasks
            if t["user_id"] == user_id
            and t["created_date"] == yesterday
            and t["status"] in ("pending", "deferred")
        ]

    async def update_task_status(self, task_id: str, status: str) -> dict:
        for t in self.tasks:
            if t["task_id"] == task_id:
                t["status"] = status
                if status == "done":
                    t["actual_completion"] = utc_now().isoformat()
                if status == "deferred":
                    t["deferred_count"] = (t.get("deferred_count") or 0) + 1
                return t
        raise ValueError(f"Task {task_id} not found")

    async def create_reminder(self, task_id, user_id, scheduled_time):
        reminder = {
            "reminder_id": str(uuid.uuid4()),
            "task_id": task_id,
            "user_id": user_id,
            "scheduled_time": scheduled_time,
            "status": "pending",
            "snooze_count": 0,
            "telegram_message_id": None,
        }
        self.reminders.append(reminder)
        return reminder

    async def update_reminder(self, reminder_id: str, updates: dict) -> dict:
        for r in self.reminders:
            if r["reminder_id"] == reminder_id:
                r.update(updates)
                return r
        raise ValueError(f"Reminder {reminder_id} not found")

    async def get_pending_reminders(self, user_id: str) -> list[dict]:
        return [
            r for r in self.reminders
            if r["user_id"] == user_id and r["status"] == "pending"
        ]

    async def get_reminder_with_task(self, reminder_id: str) -> dict | None:
        for reminder in self.reminders:
            if reminder["reminder_id"] != reminder_id:
                continue
            task = next((t for t in self.tasks if t["task_id"] == reminder["task_id"]), None)
            if not task:
                return {**reminder, "tasks": {"title": "your task", "category": "other"}}
            return {**reminder, "tasks": {"title": task["title"], "category": task["category"]}}
        return None

    async def get_reminder_for_send(self, reminder_id: str) -> dict | None:
        for reminder in self.reminders:
            if reminder["reminder_id"] != reminder_id:
                continue
            task = next((t for t in self.tasks if t["task_id"] == reminder["task_id"]), None)
            return {
                "status": reminder["status"],
                "tasks": {"status": task["status"] if task else None},
            }
        return None

    async def claim_reminder_for_send(self, reminder_id: str) -> dict | None:
        for reminder in self.reminders:
            if reminder["reminder_id"] != reminder_id or reminder["status"] != "pending":
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

    async def create_pairing_token(self, token: str, auth_id: str, expires_at: datetime) -> dict:
        """Create a new pairing token linked to a Supabase auth.uid()."""
        row = {
            "token": token,
            "supabase_auth_id": auth_id,
            "expires_at": expires_at.isoformat(),
            "consumed": False,
        }
        self.pairing_tokens[token] = row
        return dict(row)

    async def consume_pairing_token(self, token: str) -> dict | None:
        """Atomically claim/consume a pairing token if valid and not expired.

        Returns token dict if consumed successfully, otherwise None.
        """
        row = self.pairing_tokens.get(token)
        if not row:
            return None
        if row["consumed"]:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is not None:
            from zoneinfo import ZoneInfo
            expires_at = expires_at.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        from src.utils import utc_now
        if expires_at < utc_now().replace(tzinfo=None):
            return None
        row["consumed"] = True
        return dict(row)



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
