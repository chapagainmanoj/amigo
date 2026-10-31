"""Telegram message and command handlers — the glue between bot and agent."""

import logging

from src.access import OPEN_CHANNELS, help_message, may_use_channel
from src.agent.runtime import ModeRuntime
from src.bot.reminder_actions import ReminderActions
from src.bot.turns import TurnProcessor
from src.channels.base import ConversationRef, MessageChannel, Recipient
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
        *,
        channels=None,
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
            store, channel, reminder_scheduler, session_mgr, self.turn_processor.mode_runtime,
            channels=channels,
        )
        if hasattr(channel, "default_conversation_resolver"):
            channel.default_conversation_resolver = (
                self.turn_processor.modes.conversations.ensure_by_chat
            )

    async def handle_message(
        self,
        chat_id: Recipient,
        text: str,
        *,
        update_id: int = 0,
        conversation: ConversationRef | None = None,
    ) -> None:
        """Handle incoming text message from user."""
        from src.bot.pairing import handle_pairing, pairing_token

        token = pairing_token(text)
        pairing_attempt = token is not None
        if not await self._is_allowed(chat_id, pairing_attempt=pairing_attempt):
            if self.channel.capabilities.threads and conversation is None:
                return
            await self.channel.send_message(
                chat_id, "Hey! Amigo isn't open to new users yet. Stay tuned 👋",
                conversation=conversation,
            )
            return

        # Pairing: Telegram's deep link or a typed /pair command.
        if pairing_attempt:
            await handle_pairing(
                chat_id, token, self.store, self.channel, conversation=conversation
            )
            return

        # Dashboard-first Activation owns account creation and onboarding.
        user = await self._participant(chat_id)
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

        if text.strip() == "/help":
            await self.channel.send_message(chat_id, help_message(), conversation=conversation)
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
        chat_id: Recipient,
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

        if data.startswith(("handoff:", "coach:", "suggest:", "memory:", "consent:", "mode:")):
            user = await self._participant(chat_id)
            if user and user.get("supabase_auth_id"):
                activation = await self.store.get_activation_state(user["supabase_auth_id"])
                if activation.get("completed"):
                    if data.startswith("memory:"):
                        await self.memory.handle_callback(user, chat_id, data, conversation)
                    elif data.startswith("suggest:"):
                        await self.turn_processor.suggestions.handle_callback(
                            user, chat_id, data, conversation
                        )
                    elif data.startswith("mode:"):
                        # A tap on the /mode list: same path as typing /mode <id>.
                        try:
                            await self.channel.edit_message_buttons(
                                chat_id, message_id, buttons=None, conversation=conversation
                            )
                        except Exception as error:
                            # An old list may no longer be editable; still switch.
                            logger.warning("Mode list not cleared: %s", type(error).__name__)
                        mode_id = data.split(":", 1)[1]
                        if mode_id:
                            await self.turn_processor.open_mode(chat_id, user, mode_id)
                    elif data.startswith("consent:"):
                        if await self.coaching.handle_consent(user, chat_id, data, conversation):
                            # The tap answered "/mode coach": open Coach rather than ask again.
                            await self.turn_processor.open_mode(chat_id, user, "coach")
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

    async def _participant(self, chat_id: Recipient) -> dict | None:
        """The participant this channel address is linked to (ADR 0004)."""
        return await self.store.get_user_by_channel_identity(
            self.channel.channel_id, str(chat_id)
        )

    async def _send_activation_required(
        self, chat_id: Recipient, *, paired: bool = False, conversation=None
    ) -> None:
        """Direct unlinked and incomplete accounts to the verified Dashboard journey."""
        from src.config import settings

        prefix = (
            f"{self.channel.display_name} is connected. " if paired
            else "Start from your verified dashboard. "
        )
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

    async def _is_allowed(self, chat_id: Recipient, *, pairing_attempt: bool = False) -> bool:
        """Apply the configured open, closed, allowlist, or invitation access posture."""
        from src.config import settings

        if settings.access_mode == "closed":
            return False
        if self.channel.channel_id not in OPEN_CHANNELS:
            # Every posture, open included: other apps follow may_use_channel. Pairing attempts
            # reach Pairing, which applies the same rule to the token's account.
            if pairing_attempt:
                return True
            return may_use_channel(await self._participant(chat_id), self.channel.channel_id)
        if settings.access_mode == "open":
            return True
        if settings.access_mode in {"registered", "invite"}:
            if pairing_attempt:
                return True
            user = await self._participant(chat_id)
            return bool(user and user.get("supabase_auth_id"))

        try:
            allowed_ids = parse_allowed_chat_ids(settings.allowed_telegram_chat_ids)
        except UnsafeProductionConfigurationError:
            logger.error("Invalid ALLOWED_TELEGRAM_CHAT_IDS; denying Telegram access")
            return False
        return chat_id in allowed_ids
