"""Telegram message and command handlers — the glue between bot and agent."""

import logging

from src.bot.onboarding import handle_onboarding
from src.bot.reminder_actions import ReminderActions
from src.bot.turns import TurnProcessor
from src.channels.base import MessageChannel
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler

logger = logging.getLogger(__name__)


class BotHandlers:
    """Wires Telegram events to agent logic."""

    def __init__(
        self,
        channel: MessageChannel,
        store: MemoryStore,
        session_mgr: SessionManager,
        reminder_scheduler: ReminderScheduler,
    ):
        self.channel = channel
        self.store = store
        self.session_mgr = session_mgr
        self.scheduler = reminder_scheduler
        self.reminder_actions = ReminderActions(channel, store, reminder_scheduler)
        self.turn_processor = TurnProcessor(
            channel=channel,
            store=store,
            session_mgr=session_mgr,
            scheduler=reminder_scheduler,
        )

    async def handle_message(self, chat_id: int, text: str) -> None:
        """Handle incoming text message from user."""
        # Allowlist check — reject unknown users
        if not self._is_allowed(chat_id):
            await self.channel.send_message(
                chat_id, "Hey! Amigo isn't open to new users yet. Stay tuned 👋"
            )
            return

        # Deep-link pairing check
        if text.startswith("/start pair_"):
            token = text.replace("/start pair_", "").strip()
            from src.bot.pairing import handle_start_pairing
            await handle_start_pairing(chat_id, token, self.store, self.channel)
            return

        # Get or create user
        user = await self.store.get_user_by_chat_id(chat_id)

        if user is None:
            # New user — create and start onboarding
            user = await self.store.create_user(chat_id)
            await handle_onboarding(user, text, self.channel, self.store, chat_id)
            return

        if not user.get("onboarding_complete"):
            # Still onboarding
            still_onboarding = await handle_onboarding(
                user, text, self.channel, self.store, chat_id
            )
            if still_onboarding:
                return
            # Onboarding just completed — consume this message, don't process it
            return

        await self.turn_processor.handle(chat_id, user, text)

    async def handle_callback(self, chat_id: int, message_id: int, data: str) -> None:
        """Handle inline keyboard button tap."""
        # Check for onboarding callbacks
        if data.startswith("tz:") or data.startswith("onboard:"):
            user = await self.store.get_user_by_chat_id(chat_id)
            if user and not user.get("onboarding_complete"):
                await handle_onboarding(
                    user, "", self.channel, self.store, chat_id, callback_data=data
                )
                # Remove buttons after tap
                await self.channel.edit_message_buttons(chat_id, message_id, buttons=None)
                return

        await self.reminder_actions.handle_callback(chat_id, message_id, data)

    async def _cancel_reminders_for_task(self, task_id: str, user_id: str) -> None:
        """Acknowledge all pending reminders for a task and cancel APScheduler jobs."""
        await self.reminder_actions.cancel_for_task(task_id, user_id)

    def _is_allowed(self, chat_id: int) -> bool:
        """Check if chat_id is in the allowlist. Empty allowlist = allow all (dev mode)."""
        from src.config import settings
        allowed = settings.allowed_telegram_chat_ids.strip()
        if not allowed:
            return True  # No allowlist configured = open (dev convenience)
        allowed_ids = {int(x.strip()) for x in allowed.split(",") if x.strip()}
        return chat_id in allowed_ids
