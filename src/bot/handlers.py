"""Telegram message and command handlers — the glue between bot and agent."""

import logging

from src.bot.onboarding import handle_onboarding
from src.bot.reminder_actions import ReminderActions
from src.bot.turns import TurnProcessor
from src.channels.base import MessageChannel
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.runtime_config import UnsafeProductionConfigurationError, parse_allowed_chat_ids
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

    async def handle_message(self, chat_id: int, text: str, *, update_id: int = 0) -> None:
        """Handle incoming text message from user."""
        pairing_attempt = text.startswith("/start pair_")
        if not await self._is_allowed(chat_id, pairing_attempt=pairing_attempt):
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

        await self.turn_processor.handle(chat_id, user, text, update_id=update_id)

    async def handle_callback(self, chat_id: int, message_id: int, data: str) -> None:
        """Handle inline keyboard button tap."""
        if not await self._is_allowed(chat_id):
            await self.channel.send_message(
                chat_id, "Hey! Amigo isn't open to new users yet. Stay tuned 👋"
            )
            return

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

    async def _is_allowed(self, chat_id: int, *, pairing_attempt: bool = False) -> bool:
        """Apply the configured open, closed, allowlist, or invitation access posture."""
        from src.config import settings

        if settings.access_mode == "open":
            return True
        if settings.access_mode == "closed":
            return False
        if settings.access_mode == "invite":
            if pairing_attempt:
                return True
            user = await self.store.get_user_by_chat_id(chat_id)
            return bool(user and user.get("supabase_auth_id"))

        try:
            allowed_ids = parse_allowed_chat_ids(settings.allowed_telegram_chat_ids)
        except UnsafeProductionConfigurationError:
            logger.error("Invalid ALLOWED_TELEGRAM_CHAT_IDS; denying Telegram access")
            return False
        return chat_id in allowed_ids
