"""Authenticated user turn processing."""

import logging
import uuid

from src.access import trial_exhausted, trial_finished_message
from src.agent.modes import DAILY_MODE_ID
from src.agent.runtime import ModeRuntime
from src.bot.modes import ModeController
from src.channels.base import ConversationRef, MessageChannel, Recipient
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.mode_suggestions import ModeSuggestionController
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
        # Composition roots (main, cli) always pass one; the module default serves tests.
        if mode_runtime is None:
            from src.agent.runtime import default_runtime

            mode_runtime = default_runtime
        self.mode_runtime = mode_runtime
        self.turn_orchestrator = SessionTurnOrchestrator(self.mode_runtime)
        self.modes = ModeController(store, channel, scheduler, session_mgr, self.mode_runtime)
        self.suggestions = ModeSuggestionController(self.modes)

    async def handle(
        self, chat_id: Recipient, user: dict, text: str, *, update_id: int,
        conversation: ConversationRef | None = None,
    ) -> None:
        prepared = await self.modes.prepare(chat_id, user, text, update_id, conversation)
        context = prepared.context
        if prepared.response is not None:
            await self.channel.send_message(
                chat_id, prepared.response, buttons=prepared.buttons,
                conversation=context.conversation,
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
        if await trial_exhausted(self.store, user):
            await self.channel.send_message(
                chat_id, trial_finished_message(chat_id), conversation=context.conversation
            )
            return
        response = await self.turn_orchestrator.handle_turn(
            context, text, requested_mode=prepared.mode_id, mode=prepared.mode
        )
        await self.channel.send_message(chat_id, response, conversation=context.conversation)
        await self.suggestions.offer(context, text, response)

    async def open_mode(
        self, chat_id: Recipient, user: dict, mode_id: str, *, note: str | None = None
    ) -> tuple[bool, str]:
        """Do exactly what typing /mode <id> does, for a dashboard click.

        Returns whether the Mode opened and what the participant was sent. A note (a chosen
        Coach template) is sent after the intro and kept in the Mode's Session, so the Mode's
        next Turn sees it.
        """
        command = "/daily" if mode_id == DAILY_MODE_ID else f"/mode {mode_id}"
        prepared = await self.modes.prepare(chat_id, user, command, f"dashboard-{uuid.uuid4()}")
        context = prepared.context
        await self.channel.send_message(
            chat_id, prepared.response, buttons=prepared.buttons,
            conversation=context.conversation,
        )
        opened = prepared.mode is not None
        if opened and note:
            await self.channel.send_message(chat_id, note, conversation=context.conversation)
            await self.store.add_message(context.session_id, user["user_id"], "assistant", note)
        return opened, prepared.response

    async def _handle_feedback(
        self, chat_id: Recipient, user: dict, session_id: str, text: str, *, conversation=None
    ) -> None:
        feedback_text = text.replace("/feedback", "").strip()
        if feedback_text:
            await self.store.save_feedback(user["user_id"], feedback_text, session_id)
            await self.channel.send_message(chat_id, "Noted ✓", conversation=conversation)
        else:
            await self.channel.send_message(
                chat_id, "Usage: /feedback your feedback here", conversation=conversation
            )
