"""Telegram message and command handlers — the glue between bot and agent."""

import logging

from src.agent.runtime import ModeRuntime
from src.bot.reminder_actions import ReminderActions
from src.bot.turns import TurnProcessor
from src.channels.base import ConversationRef, MessageChannel
from src.coaching import CoachingController
from src.commands.base import StaleVersionError
from src.handoffs import HandoffController
from src.memory.sessions import SessionManager
from src.memory.store import MemoryStore
from src.memory_service import MemoryController, MemoryService
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
        mode_runtime: ModeRuntime | None = None,
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
            mode_runtime=mode_runtime,
        )
        from src.config import settings

        self.memory = MemoryController(
            MemoryService(store), channel, settings.dashboard_url + "/#memory"
        )
        self.coaching = CoachingController(store, channel)
        self.handoffs = HandoffController(
            store, channel, reminder_scheduler, session_mgr, self.turn_processor.mode_runtime
        )
        if hasattr(channel, "default_conversation_resolver"):
            channel.default_conversation_resolver = (
                self.turn_processor.modes.conversations.ensure_by_chat
            )

    async def handle_message(
        self,
        chat_id: int,
        text: str,
        *,
        update_id: int = 0,
        conversation: ConversationRef | None = None,
    ) -> None:
        """Handle incoming text message from user."""
        pairing_attempt = text.startswith("/start pair_")
        if not await self._is_allowed(chat_id, pairing_attempt=pairing_attempt):
            if self.channel.capabilities.threads and conversation is None:
                return
            await self.channel.send_message(
                chat_id, "Hey! Amigo isn't open to new users yet. Stay tuned 👋",
                conversation=conversation,
            )
            return

        # Deep-link pairing check
        if text.startswith("/start pair_"):
            token = text.replace("/start pair_", "").strip()
            from src.bot.pairing import handle_start_pairing

            await handle_start_pairing(
                chat_id, token, self.store, self.channel, conversation=conversation
            )
            return

        # Dashboard-first Activation owns account creation and onboarding.
        user = await self.store.get_user_by_chat_id(chat_id)
        if user is None:
            await self._send_activation_required(chat_id, conversation=conversation)
            return
        auth_id = user.get("supabase_auth_id")
        if not auth_id:
            await self._send_activation_required(chat_id, conversation=conversation)
            return
        activation = await self.store.get_activation_state(auth_id)
        if not activation.get("completed"):
            await self._send_activation_required(chat_id, paired=True, conversation=conversation)
            return

        if text.strip().split()[:1] == ["/memory"]:
            try:
                handled = await self.memory.handle(user, chat_id, text.strip(), conversation)
            except StaleVersionError:
                await self.channel.send_message(
                    chat_id,
                    "Memory settings changed. Open /memory again and review the current controls.",
                    conversation=conversation,
                )
                return
            if not handled:
                await self.channel.send_message(
                    chat_id,
                    "Use /memory to inspect saved Memory and pause controls.",
                    conversation=conversation,
                )
            return

        if text.strip().split()[:1] == ["/suggestions"]:
            await self.turn_processor.suggestions.preference(user, chat_id, text, conversation)
            return

        if text.strip() == "/program":
            await self.coaching.inspect(user, chat_id, conversation)
            return

        await self.turn_processor.handle(
            chat_id, user, text, update_id=update_id, conversation=conversation
        )

    async def handle_callback(
        self,
        chat_id: int,
        message_id: int,
        data: str,
        *,
        conversation: ConversationRef | None = None,
    ) -> None:
        """Handle inline keyboard button tap."""
        if not await self._is_allowed(chat_id):
            if self.channel.capabilities.threads and conversation is None:
                return
            await self.channel.send_message(
                chat_id, "Hey! Amigo isn't open to new users yet. Stay tuned 👋",
                conversation=conversation,
            )
            return

        if data.startswith(("handoff:", "coach:", "suggest:", "memory:")):
            user = await self.store.get_user_by_chat_id(chat_id)
            if user and user.get("supabase_auth_id"):
                activation = await self.store.get_activation_state(user["supabase_auth_id"])
                if activation.get("completed"):
                    if data.startswith("memory:"):
                        await self.memory.handle_callback(user, chat_id, data, conversation)
                    elif data.startswith("suggest:"):
                        await self.turn_processor.suggestions.handle_callback(
                            user, chat_id, data, conversation
                        )
                    elif data.startswith("coach:"):
                        await self.coaching.handle_callback(user, chat_id, data, conversation)
                    else:
                        await self.handoffs.handle_callback(
                            user, chat_id, data, conversation, message_id=message_id
                        )
            return

        # Legacy onboarding controls must not bypass Dashboard-first Activation.
        if data.startswith("tz:") or data.startswith("onboard:"):
            await self._send_activation_required(chat_id, conversation=conversation)
            await self.channel.edit_message_buttons(chat_id, message_id, buttons=None)
            return

        await self.reminder_actions.handle_callback(chat_id, message_id, data)

    async def _send_activation_required(
        self, chat_id: int, *, paired: bool = False, conversation=None
    ) -> None:
        """Direct Telegram-only and incomplete accounts to the verified Dashboard journey."""
        from src.config import settings

        prefix = "Telegram is connected. " if paired else "Start from your verified dashboard. "
        await self.channel.send_message(
            chat_id,
            prefix
            + "Finish the beta limits, profile, and private test Reminder before using Amigo: "
            + settings.dashboard_url,
            conversation=conversation,
        )

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
