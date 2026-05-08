"""Supabase CRUD operations for all entities."""

import logging
from datetime import datetime

from src.utils import local_day_utc_range, today_in_tz, utc_now, yesterday_in_tz

logger = logging.getLogger(__name__)


class MemoryStore:
    """All Supabase read/write operations in one place."""

    def __init__(self):
        from src.db.supabase import get_supabase

        self.db = get_supabase()

    # ── User Profiles ──

    async def get_user_by_chat_id(self, chat_id: int) -> dict | None:
        """Find user by Telegram chat ID. Returns None if not onboarded."""
        result = (
            self.db.table("user_profiles")
            .select("*")
            .eq("telegram_chat_id", chat_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    async def create_user(self, chat_id: int) -> dict:
        """Create a new user profile during onboarding."""
        result = (
            self.db.table("user_profiles")
            .insert({"telegram_chat_id": chat_id})
            .execute()
        )
        return result.data[0]

    async def update_user(self, user_id: str, updates: dict) -> dict:
        """Update user profile fields."""
        updates["updated_at"] = utc_now().isoformat()
        result = (
            self.db.table("user_profiles")
            .update(updates)
            .eq("user_id", user_id)
            .execute()
        )
        return result.data[0]

    # ── Sessions ──

    async def get_active_session(self, user_id: str) -> dict | None:
        """Get the current open session (ended_at is NULL)."""
        result = (
            self.db.table("sessions")
            .select("*")
            .eq("user_id", user_id)
            .is_("ended_at", "null")
            .order("started_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    async def create_session(self, user_id: str, session_type: str = "casual") -> dict:
        """Start a new session."""
        result = (
            self.db.table("sessions")
            .insert({
                "user_id": user_id,
                "session_type": session_type,
            })
            .execute()
        )
        return result.data[0]

    async def close_session(self, session_id: str, summary: str | None = None) -> None:
        """Close a session with optional context summary."""
        self.db.table("sessions").update({
            "ended_at": utc_now().isoformat(),
            "context_summary": summary,
        }).eq("session_id", session_id).execute()

    async def touch_session(self, session_id: str) -> None:
        """Update last_activity_at and increment message_count."""
        # Note: message_count increment is approximate; fine for Phase 1a
        session = (
            self.db.table("sessions")
            .select("message_count")
            .eq("session_id", session_id)
            .single()
            .execute()
        )
        self.db.table("sessions").update({
            "last_activity_at": utc_now().isoformat(),
            "message_count": (session.data["message_count"] or 0) + 1,
        }).eq("session_id", session_id).execute()

    # ── Messages ──

    async def add_message(
        self, session_id: str, user_id: str, role: str, content: str, channel: str = "telegram"
    ) -> dict:
        """Store a conversation message."""
        result = (
            self.db.table("messages")
            .insert({
                "session_id": session_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "channel": channel,
            })
            .execute()
        )
        return result.data[0]

    async def get_session_messages(self, session_id: str) -> list[dict]:
        """Get all messages in a session, ordered by time."""
        result = (
            self.db.table("messages")
            .select("role, content, created_at")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
        )
        return result.data

    async def has_session_on_local_day(self, user_id: str, timezone: str) -> bool:
        """Return whether the user has any session that started today locally."""
        start_utc, end_utc = local_day_utc_range(timezone)
        result = (
            self.db.table("sessions")
            .select("session_id")
            .eq("user_id", user_id)
            .gte("started_at", start_utc.isoformat())
            .lt("started_at", end_utc.isoformat())
            .limit(1)
            .execute()
        )
        return bool(result.data)

    async def get_yesterday_summary(self, user_id: str, timezone: str) -> str | None:
        """Get the most recent closed session summary from yesterday locally."""
        yesterday = yesterday_in_tz(timezone)
        start_utc, end_utc = local_day_utc_range(timezone, yesterday)
        result = (
            self.db.table("sessions")
            .select("context_summary")
            .eq("user_id", user_id)
            .gte("started_at", start_utc.isoformat())
            .lt("started_at", end_utc.isoformat())
            .not_.is_("context_summary", "null")
            .order("ended_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return result.data["context_summary"]
        return None

    # ── Tasks ──

    async def create_task(self, user_id: str, title: str, category: str = "other",
                          session_id: str | None = None,
                          suggested_time: str | None = None,
                          timezone: str = "UTC") -> dict:
        """Create a new task. Sets created_date in user's timezone."""
        data = {
            "user_id": user_id,
            "title": title,
            "category": category,
            "source_session_id": session_id,
            "created_date": today_in_tz(timezone).isoformat(),
        }
        if suggested_time:
            data["suggested_time"] = suggested_time
        result = self.db.table("tasks").insert(data).execute()
        return result.data[0]

    async def get_today_tasks(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        """Get all tasks for today (in user's timezone, not server's)."""
        today = today_in_tz(timezone).isoformat()
        result = (
            self.db.table("tasks")
            .select("*")
            .eq("user_id", user_id)
            .eq("created_date", today)
            .order("created_at")
            .execute()
        )
        return result.data

    async def get_yesterday_pending(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        """Get yesterday's incomplete tasks (in user's timezone)."""
        yesterday = yesterday_in_tz(timezone).isoformat()
        result = (
            self.db.table("tasks")
            .select("*")
            .eq("user_id", user_id)
            .eq("created_date", yesterday)
            .in_("status", ["pending", "deferred"])
            .execute()
        )
        return result.data

    async def update_task_status(self, task_id: str, status: str) -> dict:
        """Update task status. Handles deferred_count increment."""
        updates: dict = {"status": status}
        if status == "done":
            updates["actual_completion"] = utc_now().isoformat()
        if status == "deferred":
            # Increment deferred_count
            task = self.db.table("tasks").select("deferred_count").eq(
                "task_id", task_id).single().execute()
            updates["deferred_count"] = (task.data["deferred_count"] or 0) + 1
        result = self.db.table("tasks").update(updates).eq("task_id", task_id).execute()
        return result.data[0]

    # ── Reminders ──

    async def create_reminder(self, task_id: str, user_id: str,
                              scheduled_time: str) -> dict:
        """Schedule a reminder for a task."""
        result = (
            self.db.table("reminders")
            .insert({
                "task_id": task_id,
                "user_id": user_id,
                "scheduled_time": scheduled_time,
            })
            .execute()
        )
        return result.data[0]

    async def update_reminder(self, reminder_id: str, updates: dict) -> dict:
        """Update reminder fields (status, snooze_count, telegram_message_id)."""
        result = (
            self.db.table("reminders")
            .update(updates)
            .eq("reminder_id", reminder_id)
            .execute()
        )
        return result.data[0]

    async def get_pending_reminders(self, user_id: str) -> list[dict]:
        """Get all pending reminders for a user."""
        result = (
            self.db.table("reminders")
            .select("*, tasks(title, category)")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .order("scheduled_time")
            .execute()
        )
        return result.data

    async def get_reminder_with_task(self, reminder_id: str) -> dict | None:
        """Fetch a reminder with task title/category for callback handling."""
        result = (
            self.db.table("reminders")
            .select("*, tasks(title, category)")
            .eq("reminder_id", reminder_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    async def get_reminder_for_send(self, reminder_id: str) -> dict | None:
        """Fetch reminder/task status immediately before sending a reminder."""
        result = (
            self.db.table("reminders")
            .select("status, tasks(status)")
            .eq("reminder_id", reminder_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    async def get_pending_reminders_for_reload(self, cutoff: datetime) -> list[dict]:
        """Get pending reminders due after cutoff with task title and chat id."""
        result = (
            self.db.table("reminders")
            .select("*, tasks(title), user_profiles!reminders_user_id_fkey(telegram_chat_id)")
            .eq("status", "pending")
            .gte("scheduled_time", cutoff.isoformat())
            .execute()
        )
        return result.data

    async def acknowledge_reminders_for_task(self, task_id: str, user_id: str) -> list[str]:
        """Mark all pending reminders for a task as acknowledged.

        Returns list of reminder_ids so caller can cancel APScheduler jobs.
        """
        result = (
            self.db.table("reminders")
            .select("reminder_id")
            .eq("task_id", task_id)
            .eq("user_id", user_id)
            .eq("status", "pending")
            .execute()
        )
        reminder_ids = [r["reminder_id"] for r in result.data]

        if reminder_ids:
            (
                self.db.table("reminders")
                .update({"status": "acknowledged"})
                .eq("task_id", task_id)
                .eq("user_id", user_id)
                .eq("status", "pending")
                .execute()
            )

        return reminder_ids

    # ── Feedback ──

    async def save_feedback(self, user_id: str, content: str,
                            session_id: str | None = None) -> dict:
        """Store user feedback from /feedback command."""
        result = (
            self.db.table("feedback")
            .insert({
                "user_id": user_id,
                "content": content,
                "session_id": session_id,
            })
            .execute()
        )
        return result.data[0]

    # ── Usage Events ──

    async def log_usage(self, user_id: str, model: str, input_tokens: int,
                        output_tokens: int, session_id: str | None = None) -> None:
        """Log LLM usage for cost tracking."""
        # Rough cost estimation (Gemini Flash pricing)
        cost_per_m_input = 0.15
        cost_per_m_output = 0.60
        estimated_cost = (
            (input_tokens / 1_000_000) * cost_per_m_input
            + (output_tokens / 1_000_000) * cost_per_m_output
        )
        self.db.table("usage_events").insert({
            "user_id": user_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimated_cost,
            "session_id": session_id,
        }).execute()
