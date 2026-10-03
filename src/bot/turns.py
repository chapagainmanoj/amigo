"""Authenticated user turn processing."""

import logging

from src.agent.runtime import ModeRuntime, default_runtime
from src.channels.base import MessageChannel
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler
from src.tools.context import ToolContext
from src.turns import SessionTurnOrchestrator

logger = logging.getLogger(__name__)


class TurnProcessor:
    """Routes one authenticated, onboarded Telegram message."""

    def __init__(
        self,
        channel: MessageChannel,
        store: MemoryStore,
        session_mgr: SessionManager,
        scheduler: ReminderScheduler,
        mode_runtime: ModeRuntime | None = None,
    ):
        self.channel = channel
        self.store = store
        self.session_mgr = session_mgr
        self.scheduler = scheduler
        self.mode_runtime = mode_runtime or default_runtime
        self.turn_orchestrator = SessionTurnOrchestrator(self.mode_runtime)

    async def handle(self, chat_id: int, user: dict, text: str, *, update_id: int) -> None:
        """Handle regular message flow after access control and onboarding."""
        timeout = user.get("session_timeout_minutes", 120)
        user_tz = user.get("timezone") or "UTC"
        session, _is_new = await self.session_mgr.get_or_create_session(
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

        context = ToolContext(
            store=self.store,
            scheduler=self.scheduler,
            channel=self.channel,
            user=user,
            session_id=session_id,
            chat_id=chat_id,
            timezone=user_tz,
            turn_id=str(update_id),
        )
        response = await self.turn_orchestrator.handle_turn(context, text)
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
