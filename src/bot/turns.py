"""Authenticated user turn processing."""

import logging

from src.agent.amigo import AmigoAgent
from src.bot.reminder_actions import ReminderActions
from src.bot.task_matching import TaskMatcher
from src.channels.base import MessageChannel
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore

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
    ):
        self.agent = agent
        self.channel = channel
        self.store = store
        self.session_mgr = session_mgr
        self.reminder_actions = reminder_actions
        self.task_matcher = task_matcher or TaskMatcher()

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

        if await self._handle_status_update(chat_id, user, session_id, text, user_tz):
            return

        if await self._handle_task_list(chat_id, user, session, is_new, session_id, text, user_tz):
            return

        if is_new and session.get("session_type") == "morning_planning":
            response = await self.agent.morning_planning(user, session_id, text)
        else:
            response = await self.agent.chat(user, session_id, text)

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

    async def _handle_status_update(
        self, chat_id: int, user: dict, session_id: str, text: str, user_tz: str
    ) -> bool:
        pending = await self.store.get_today_tasks(user["user_id"], user_tz)
        pending_tasks = [t for t in pending if t["status"] in ("pending", "deferred")]

        status_update = await self.agent.detect_status_update(text, pending_tasks)
        if not status_update:
            return False

        matched = self.task_matcher.fuzzy_match_task(
            status_update.task_title_match, pending_tasks
        )
        if not matched:
            return False

        await self.store.add_message(session_id, user["user_id"], "user", text)
        await self.store.update_task_status(matched["task_id"], status_update.new_status)
        await self.reminder_actions.cancel_for_task(matched["task_id"], user["user_id"])
        await self.store.add_message(
            session_id, user["user_id"], "assistant", status_update.response_message
        )
        await self.channel.send_message(chat_id, status_update.response_message)
        return True

    async def _handle_task_list(
        self,
        chat_id: int,
        user: dict,
        session: dict,
        is_new: bool,
        session_id: str,
        text: str,
        user_tz: str,
    ) -> bool:
        if not self.task_matcher.looks_like_task_list(text):
            return False

        try:
            extraction = await self.agent.extract_tasks(text)
            await self.store.add_message(session_id, user["user_id"], "user", text)

            for task in extraction.tasks:
                created = await self.store.create_task(
                    user_id=user["user_id"],
                    title=task.title,
                    category=task.category,
                    session_id=session_id,
                    timezone=user_tz,
                )
                if task.reminder_time:
                    await self.reminder_actions.schedule_for_task(
                        user, created, task.reminder_time, chat_id
                    )

            response = extraction.confirmation_message
            if extraction.unextracted:
                response += (
                    f"\n\n🤔 I wasn't sure about: \"{extraction.unextracted}\" — "
                    "what did you mean?"
                )

            if is_new and session.get("session_type") == "morning_planning":
                morning = await self.agent.morning_planning(user, session_id, "")
                response = morning + "\n\n" + response

            await self.store.add_message(session_id, user["user_id"], "assistant", response)
            await self.channel.send_message(chat_id, response)
            return True

        except Exception:
            logger.exception("Task extraction failed, falling back to chat")
            return False
