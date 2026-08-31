"""LLM context fragments for summaries, tasks, and bounded session history."""

import logging

from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# Hard cap for session messages in context
MAX_CONTEXT_TOKENS = 3000
CHARS_PER_TOKEN = 4  # Rough approximation


class ContextBuilder:
    """Builds the context fragments used by the agent for each LLM call."""

    def __init__(self, store: MemoryStore):
        self.store = store

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
                status_emoji = {
                    "pending": "⏳",
                    "completed": "✅",
                    "skipped": "⏭️",
                    "cancelled": "🚫",
                }
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
