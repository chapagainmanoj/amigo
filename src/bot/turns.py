"""Authenticated user turn processing."""

import logging

from src.agent.runtime import ModeRuntime, default_runtime
from src.bot.modes import ModeController
from src.channels.base import ConversationRef, MessageChannel
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler
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
        self.modes = ModeController(store, channel, scheduler, session_mgr, self.mode_runtime)

    async def handle(
        self, chat_id: int, user: dict, text: str, *, update_id: int,
        conversation: ConversationRef | None = None,
    ) -> None:
        prepared = await self.modes.prepare(chat_id, user, text, update_id, conversation)
        context = prepared.context
        if prepared.response is not None:
            await self.channel.send_message(
                chat_id, prepared.response, conversation=context.conversation
            )
            return
        if prepared.mode_id == "coach":
            program = await self.store.get_coaching_program(user["user_id"])
            if program is not None:
                await self.store.note_coaching_reply(user["user_id"], program["program_id"])
        if await self.session_mgr.should_close(text):
            await self.store.close_session(context.session_id)
            await self.channel.send_message(
                chat_id, "Night! 🌙 Talk tomorrow.", conversation=context.conversation
            )
            return
        if text.startswith("/feedback"):
            await self._handle_feedback(
                chat_id, user, context.session_id, text, conversation=context.conversation
            )
            return
        response = await self.turn_orchestrator.handle_turn(
            context, text, requested_mode=prepared.mode_id
        )
        await self.channel.send_message(chat_id, response, conversation=context.conversation)

    async def _handle_feedback(
        self, chat_id: int, user: dict, session_id: str, text: str, *, conversation=None
    ) -> None:
        feedback_text = text.replace("/feedback", "").strip()
        if feedback_text:
            await self.store.save_feedback(user["user_id"], feedback_text, session_id)
            await self.channel.send_message(chat_id, "Noted ✓", conversation=conversation)
        else:
            await self.channel.send_message(
                chat_id, "Usage: /feedback your feedback here", conversation=conversation
            )
