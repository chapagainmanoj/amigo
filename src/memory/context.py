"""LLM context assembly — most perf-sensitive path.

Assembles in chronological order:
1. System prompt (from prompts.py)
2. User profile block (name, timezone, coaching profile)
3. Yesterday's summary (from last closed session's context_summary)
4. Today's tasks + status
5. Current session messages (newest-first truncation at 3K token cap)
"""

import logging

from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# Hard cap for session messages in context
MAX_CONTEXT_TOKENS = 3000
CHARS_PER_TOKEN = 4  # Rough approximation


class ContextBuilder:
    """Builds the full context payload for each LLM call."""

    def __init__(self, store: MemoryStore):
        self.store = store

    async def build(self, user: dict, session_id: str) -> list[dict[str, str]]:
        """Assemble conversation history for LLM.

        Returns list of message dicts for context assembly.
        """
        parts = []

        # 1. User profile context (injected as system-adjacent user message)
        profile_block = self._build_profile_block(user)
        parts.append({"role": "user", "content": profile_block})
        parts.append({"role": "assistant", "content": "Got it, I have your context loaded."})

        # 2. Yesterday's summary
        user_tz = user.get("timezone") or "UTC"
        yesterday_summary = await self._get_yesterday_summary(user["user_id"], user_tz)
        if yesterday_summary:
            parts.append({"role": "user", "content": f"[Yesterday's summary]\n{yesterday_summary}"})
            parts.append({"role": "assistant", "content": "Noted, I remember yesterday."})

        # 3. Today's tasks
        tasks_block = await self._build_tasks_block(user["user_id"], user_tz)
        if tasks_block:
            parts.append({"role": "user", "content": f"[Today's tasks]\n{tasks_block}"})
            parts.append({"role": "assistant", "content": "I see today's task list."})

        # 4. Session messages (with token cap, newest-first truncation)
        session_messages = await self._get_truncated_messages(session_id)
        parts.extend(session_messages)

        return parts

    def _build_profile_block(self, user: dict) -> str:
        """Build user profile context string."""
        name = user.get("name") or "friend"
        tz = user.get("timezone") or "unknown"
        wake = user.get("wake_time") or "07:30"
        return (
            f"[User profile]\n"
            f"Name: {name}\n"
            f"Timezone: {tz}\n"
            f"Wake time: {wake}\n"
        )

    async def _get_yesterday_summary(self, user_id: str, timezone: str) -> str | None:
        """Get the most recent closed session's summary from yesterday (user's timezone)."""
        return await self.store.get_yesterday_summary(user_id, timezone)

    async def _build_tasks_block(self, user_id: str, timezone: str) -> str | None:
        """Build a concise task status string for context."""
        today_tasks = await self.store.get_today_tasks(user_id, timezone)
        yesterday_pending = await self.store.get_yesterday_pending(user_id, timezone)

        lines = []
        if yesterday_pending:
            lines.append("Carried over from yesterday:")
            for t in yesterday_pending:
                lines.append(f"  - {t['title']} (still {t['status']})")

        if today_tasks:
            lines.append("Today:")
            for t in today_tasks:
                status_emoji = {"pending": "⏳", "done": "✅", "skipped": "⏭️", "deferred": "🔄"}
                emoji = status_emoji.get(t["status"], "❓")
                lines.append(f"  {emoji} {t['title']}")

        return "\n".join(lines) if lines else None

    async def _get_truncated_messages(self, session_id: str) -> list[dict[str, str]]:
        """Get session messages, truncated to fit within token budget.

        Keeps newest messages first (most relevant), drops oldest if over budget.
        """
        messages = await self.store.get_session_messages(session_id)
        if not messages:
            return []

        result = []
        token_count = 0
        # Walk backwards (newest first) and collect until budget exhausted
        for msg in reversed(messages):
            msg_tokens = len(msg["content"]) // CHARS_PER_TOKEN
            if token_count + msg_tokens > MAX_CONTEXT_TOKENS:
                break
            result.append({"role": msg["role"], "content": msg["content"]})
            token_count += msg_tokens

        # Reverse back to chronological order
        result.reverse()
        return result
