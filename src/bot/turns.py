"""Authenticated user turn processing."""

import logging

from src.agent.amigo import AmigoAgent
from src.bot.reminder_actions import ReminderActions
from src.bot.task_matching import TaskMatcher
from src.channels.base import MessageChannel
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.tools import ToolExecutionContext, ToolExecutor

logger = logging.getLogger(__name__)


class TurnProcessor:
    """Routes one authenticated, onboarded Telegram message."""

    def __init__(
        self,
        agent: AmigoAgent,
        channel: MessageChannel,
        store: MemoryStore,
        session_mgr: SessionManager,
        reminder_actions: ReminderActions,
        task_matcher: TaskMatcher | None = None,
        tool_executor: ToolExecutor | None = None,
    ):
        self.agent = agent
        self.channel = channel
        self.store = store
        self.session_mgr = session_mgr
        self.reminder_actions = reminder_actions
        self.task_matcher = task_matcher or TaskMatcher()
        self.tool_executor = tool_executor or ToolExecutor(store, reminder_actions.scheduler)

    async def handle(self, chat_id: int, user: dict, text: str) -> None:
        """Handle regular message flow after access control and onboarding."""
        timeout = user.get("session_timeout_minutes", 120)
        user_tz = user.get("timezone") or "UTC"
        session, is_new = await self.session_mgr.get_or_create_session(
            user["user_id"], timeout, timezone=user_tz
        )
        session_id = session["session_id"]

        if await self.session_mgr.should_close(text):
            await self.store.close_session(session_id)
            await self.channel.send_message(chat_id, "Night! 🌙 Talk tomorrow.")
            return

        if text.startswith("/feedback"):
            await self._handle_feedback(chat_id, user, session_id, text)
            return

        pending = await self.store.get_today_tasks(user["user_id"], user_tz)
        pending_tasks = [t for t in pending if t["status"] in ("pending", "deferred")]
        try:
            decision = await self.agent.plan_message(user, text, pending_tasks, user_tz)
        except Exception:
            logger.exception("Agent planning failed, falling back to chat")
            decision = None

        if decision is None or decision.message_type == "chat":
            if is_new and session.get("session_type") == "morning_planning":
                response = await self.agent.morning_planning(user, session_id, text)
            else:
                response = await self.agent.chat(user, session_id, text)
            await self.channel.send_message(chat_id, response)
            return

        await self.store.add_message(session_id, user["user_id"], "user", text)
        await self.tool_executor.execute(
            decision.tool_calls,
            ToolExecutionContext(
                user=user,
                session_id=session_id,
                chat_id=chat_id,
                timezone=user_tz,
            ),
        )

        response = decision.reply or ""
        if is_new and session.get("session_type") == "morning_planning":
            morning = await self.agent.morning_planning(user, session_id, "")
            response = morning + "\n\n" + response if response else morning

        if response:
            await self.store.add_message(session_id, user["user_id"], "assistant", response)
            await self.channel.send_message(chat_id, response)

    async def _handle_feedback(
        self, chat_id: int, user: dict, session_id: str, text: str
    ) -> None:
        feedback_text = text.replace("/feedback", "").strip()
        if feedback_text:
            await self.store.save_feedback(user["user_id"], feedback_text, session_id)
            await self.channel.send_message(chat_id, "Noted ✓")
        else:
            await self.channel.send_message(chat_id, "Usage: /feedback your feedback here")
