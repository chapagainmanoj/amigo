"""Shared fakes for testing — no real Supabase, Telegram, or Gemini needed.

These fakes implement the same interfaces as production classes but store
everything in-memory dictionaries. They're intentionally simple — just enough
to test behavior, not to replicate Supabase query semantics.
"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.channels.base import ChannelCapabilities, ConversationRef
from src.commands.base import (
    IdempotencyConflictError,
    InvalidTransitionError,
    StaleVersionError,
)
from src.memory.activation import (
    acknowledge_terms,
    activation_state,
    create_test,
    update_profile,
)
from src.memory.coaching import LocalCoachingState
from src.memory.durable import LocalMemoryState
from src.memory.identities import (
    LocalIdentityState,
    claim_telegram,
    delivery_columns,
    finish_claim,
    live_token_owner,
    telegram_claim_ids,
    telegram_update_as_channel,
)
from src.memory.later import apply_later_transition
from src.memory.modes import LocalModeState, ModeGrant, ModeGrantResult, ModeResult
from src.memory.pairing import (
    PAIRING_TOKEN_LIMIT,
    PAIRING_TOKEN_WINDOW,
    ActivationTermsRequiredError,
    PairingTokenRateLimitError,
)
from src.memory.proactive import LocalProactiveState, reminder_budget_transaction
from src.memory.reminders import validate_reminder_timing, validate_reminder_updates
from src.memory.tasks import validate_task_status
from src.schema import EXPECTED_SCHEMA_VERSION, require_schema_version
from src.utils import utc_now


def _utc_timestamp(value: str | datetime) -> datetime:
    """Interpret legacy naive timestamps as UTC; preserve explicitly offset instants."""
    instant = datetime.fromisoformat(value) if isinstance(value, str) else value
    return (
        instant.replace(tzinfo=ZoneInfo("UTC"))
        if instant.tzinfo is None else instant.astimezone(ZoneInfo("UTC"))
    )


def _elapsed_ms(later: str, earlier: str) -> int:
    later_time = datetime.fromisoformat(later)
    earlier_time = datetime.fromisoformat(earlier)
    if later_time.tzinfo is not None:
        later_time = later_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    if earlier_time.tzinfo is not None:
        earlier_time = earlier_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return max(0, round((later_time - earlier_time).total_seconds() * 1000))


class FakeChannel:
    """In-memory message channel. Records all sent messages for assertions."""

    def __init__(self, *, threads=False, channel_id="telegram"):
        self.channel_id = channel_id
        self.display_name = "Telegram" if channel_id == "telegram" else channel_id
        self.capabilities = ChannelCapabilities(threads=threads, actions=True, message_editing=True)
        self.conversations: list[ConversationRef] = []
        self.closed_conversations: list[ConversationRef] = []
        self.sent: list[dict] = []  # [{chat_id, text, buttons}]
        self.edited: list[dict] = []

    async def send_message(
        self, chat_id: str | int, text: str, *, buttons=None, conversation=None
    ) -> int | None:
        msg_id = len(self.sent) + 1
        self.sent.append({
            "chat_id": chat_id,
            "text": text,
            "buttons": buttons,
            "message_id": msg_id,
        })
        if conversation is not None:
            self.sent[-1]["conversation"] = conversation
        return msg_id

    async def edit_message_buttons(
        self, chat_id, message_id, *, buttons=None, conversation=None
    ):
        self.edited.append({"chat_id": chat_id, "message_id": message_id, "buttons": buttons})
        if conversation is not None:
            self.edited[-1]["conversation"] = conversation

    async def create_conversation(self, chat_id, name):
        endpoint = {"chat_id": chat_id}
        if self.capabilities.threads:
            endpoint["conversation_id"] = len(self.conversations) + 1
        conversation = ConversationRef(self.channel_id, endpoint)
        self.conversations.append(conversation)
        return conversation

    async def close_conversation(self, chat_id, conversation):
        self.closed_conversations.append(conversation)

    async def conversation_link(self, conversation):
        return None

    async def recipient_matches(self, conversation, recipient):
        return conversation.channel == self.channel_id and str(
            conversation.endpoint.get("chat_id")
        ) == str(recipient)

    async def recipient_for(self, user):
        return user.get("telegram_chat_id") or user.get("chat_id")

    @property
    def last_text(self) -> str:
        return self.sent[-1]["text"] if self.sent else ""

    @property
    def texts(self) -> list[str]:
        return [m["text"] for m in self.sent]


class FakeStore:
    """In-memory store. Mimics MemoryStore's async interface with dicts."""

    def __init__(self):
        self.users: dict[str, dict] = {}  # user_id -> user
        self.sessions: list[dict] = []
        self.messages: list[dict] = []
        self.tasks: list[dict] = []
        self.reminders: list[dict] = []
        self.feedback: list[dict] = []
        self.usage: list[dict] = []
        self.pairing_tokens: dict[str, dict] = {}
        self.command_receipts: dict[tuple[str, str], dict] = {}
        self.scheduler_outbox: dict[str, dict] = {}
        self.telegram_updates: dict[int, dict] = {}
        self.reminder_occurrences: dict[str, dict] = {}
        self.reminder_delivery_attempts: dict[str, dict] = {}
        self.scheduler_runtime: dict | None = None
        self.activation_journeys: dict[str, dict] = {}
        self.schema_version = EXPECTED_SCHEMA_VERSION
        self._mode_state = LocalModeState()
        self._coaching_state = LocalCoachingState()
        self._proactive_state = LocalProactiveState()
        self._memory_state = LocalMemoryState()
        self._identity_state = LocalIdentityState()
        # Fake Supabase client for direct queries (used by SessionManager)
        self.db = FakeDB(self)

    async def connect(self) -> None:
        """Match MemoryStore startup without creating an external client."""
        return None

    async def verify_schema_version(self, expected: int) -> int:
        """Mirror the production Store's exact schema gate."""
        return require_schema_version(self.schema_version, expected)

    async def get_command_receipt(self, user_id: str, idempotency_key: str) -> dict | None:
        return copy.deepcopy(self.command_receipts.get((user_id, idempotency_key)))

    async def get_user_by_id(self, user_id: str) -> dict | None:
        user = next((row for row in self.users.values() if row["user_id"] == user_id), None)
        return copy.deepcopy(user) if user else None

    async def get_user_by_chat_id(self, chat_id: int) -> dict | None:
        return next(
            (user for user in self.users.values() if user.get("telegram_chat_id") == chat_id),
            None,
        )

    async def create_user(self, chat_id: int) -> dict:
        return self._insert_user({"telegram_chat_id": chat_id})

    def _insert_user(self, fields: dict, *, identity: tuple[str, str] | None = None) -> dict:
        user_id = str(uuid.uuid4())
        user = {
            "user_id": user_id,
            "telegram_chat_id": None,
            "primary_channel": "telegram",
            "name": None,
            "timezone": None,
            "onboarding_step": 0,
            "onboarding_complete": False,
            "wake_time": "07:30",
            "sleep_time": "23:00",
            "session_timeout_minutes": 120,
            "updated_at": utc_now().isoformat(),
        }
        self._identity_state.write_profile(
            user, {**fields, "user_id": user_id}, identity=identity
        )
        self.users[user_id] = user
        return user

    async def update_user(self, user_id: str, updates: dict) -> dict:
        user = self.users.get(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")
        return self._identity_state.write_profile(user, updates)

    async def get_user_by_channel_identity(self, channel: str, external_id: str) -> dict | None:
        user_id = self._identity_state.owner(channel, external_id)
        return await self.get_user_by_id(user_id) if user_id else None

    async def list_channel_identities(self, user_id: str) -> dict[str, str]:
        return self._identity_state.for_user(user_id)

    async def set_primary_channel(self, user_id: str, channel: str) -> str:
        if user_id not in self.users:
            raise ValueError("user_not_found")
        await self.update_user(user_id, {"primary_channel": channel})
        return channel

    async def claim_channel_update(self, channel, update_id, external_id, update_kind):
        if channel == "telegram":
            return telegram_update_as_channel(await self.claim_telegram_update(
                *telegram_claim_ids(update_id, external_id), update_kind
            ))
        return self._identity_state.claim_update(channel, update_id, external_id, update_kind)

    async def finish_channel_update(self, channel, update_id, *, status, failure_code=None):
        if channel == "telegram":
            return telegram_update_as_channel(await self.finish_telegram_update(
                telegram_claim_ids(update_id)[0], status=status, failure_code=failure_code
            ))
        return self._identity_state.finish_update(
            channel, update_id, status=status, failure_code=failure_code
        )

    async def claim_telegram_update(self, update_id, chat_id, update_kind):
        return claim_telegram(self.telegram_updates, update_id, chat_id, update_kind)

    async def finish_telegram_update(
        self, update_id, *, status, failure_code=None
    ):
        return finish_claim(
            self.telegram_updates.get(update_id), status=status, failure_code=failure_code,
            label="telegram",
        )

    async def get_active_session(self, user_id: str, mode_id: str = "daily") -> dict | None:
        for s in reversed(self.sessions):
            if (s["user_id"] == user_id and s.get("mode_id", "daily") == mode_id
                    and s.get("ended_at") is None):
                return s
        return None

    async def create_session(
        self, user_id: str, session_type: str = "casual", mode_id: str = "daily"
    ) -> dict:
        session = {
            "session_id": str(uuid.uuid4()),
            "user_id": user_id,
            "session_type": session_type,
            "mode_id": mode_id,
            "started_at": utc_now().isoformat(),
            "last_activity_at": utc_now().isoformat(),
            "ended_at": None,
            "message_count": 0,
            "context_summary": None,
            "active_mode_id": None if mode_id == "daily" else mode_id,
        }
        self.sessions.append(session)
        return session

    async def close_session(self, session_id: str, summary: str | None = None) -> None:
        for s in self.sessions:
            if s["session_id"] == session_id:
                s["ended_at"] = utc_now().isoformat()
                s["context_summary"] = summary

    async def touch_session(self, session_id: str) -> None:
        for s in self.sessions:
            if s["session_id"] == session_id:
                s["last_activity_at"] = utc_now().isoformat()
                s["message_count"] = (s.get("message_count") or 0) + 1

    async def add_message(self, session_id, user_id, role, content, channel="telegram"):
        msg = {
            "message_id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "channel": channel,
            "created_at": utc_now().isoformat(),
        }
        self.messages.append(msg)
        return msg

    # ── Session Modes, trial grants, and confirmed handoffs ──

    async def get_active_mode(self, user_id: str, session_id: str) -> str | None:
        sessions = {row["session_id"]: row for row in self.sessions}
        return await self._mode_state.get_mode(sessions, user_id, session_id)

    async def set_active_mode(
        self, user_id: str, session_id: str, mode_id: str | None, *, grant_required: bool = True,
    ) -> ModeResult:
        """grant_required is derived by trusted registry code, never by model arguments."""
        sessions = {row["session_id"]: row for row in self.sessions}
        return await self._mode_state.set_mode(
            sessions, user_id, session_id, mode_id, grant_required,
        )

    async def grant_mode(
        self, user_id: str, mode_id: str, operator: str, reason: str,
        expires_at: datetime | None = None,
    ) -> ModeGrantResult:
        return await self._mode_state.grant(
            self.users.values(), user_id, mode_id, operator, reason, expires_at,
        )

    async def revoke_mode_grant(
        self, user_id: str, mode_id: str, operator: str, reason: str,
    ) -> ModeGrantResult:
        return await self._mode_state.revoke(user_id, mode_id, operator, reason)

    async def get_active_mode_grant(self, user_id: str, mode_id: str) -> ModeGrant | None:
        return await self._mode_state.get_active_grant(user_id, mode_id)

    async def create_handoff(
        self, user_id: str, session_id: str, source_mode_id: str, target_mode_id: str,
        carried_request: str, *, source_grant_required: bool = True,
        target_grant_required: bool = True,
    ) -> ModeResult:
        """Flags come from trusted registry definitions and persist for later resolution."""
        sessions = {row["session_id"]: row for row in self.sessions}
        return await self._mode_state.create_handoff(
            sessions, user_id, session_id, source_mode_id, target_mode_id,
            carried_request, source_grant_required, target_grant_required,
        )

    async def resolve_handoff(
        self, user_id: str, session_id: str, handoff_id: str, confirm: bool,
    ) -> ModeResult:
        """Return a carried request only after atomic confirmation; never execute it here."""
        sessions = {row["session_id"]: row for row in self.sessions}
        return await self._mode_state.resolve_handoff(
            sessions, user_id, session_id, handoff_id, confirm,
        )

    async def get_memory_settings(self, user_id):
        await self._memory_user(user_id)
        return await self._memory_state.get_settings(user_id)

    async def prepare_memory_confirmation(
        self,
        user_id,
        operation,
        preview_digest,
        expected_settings_version,
        memory_id=None,
        expected_memory_version=None,
    ):
        await self._memory_user(user_id)
        return await self._memory_state.prepare(
            user_id,
            operation,
            preview_digest,
            expected_settings_version,
            memory_id,
            expected_memory_version,
        )

    async def confirm_memory_save(
        self,
        user_id,
        token,
        payload,
        idempotency_key,
        payload_hash,
        enable_memory=False,
        policy_version=None,
    ):
        user = await self._memory_user(user_id)
        return await self._memory_state.confirm(
            user,
            self.messages,
            {row["session_id"]: row for row in self.sessions},
            token,
            payload,
            idempotency_key,
            payload_hash,
            enable_memory,
            policy_version,
        )

    async def transition_memory(
        self, user_id, memory_id, expected_version, action, idempotency_key, payload_hash
    ):
        return await self._memory_state.transition(
            await self._memory_user(user_id),
            memory_id,
            expected_version,
            action,
            idempotency_key,
            payload_hash,
        )

    async def set_memory_pauses(
        self, user_id, expected_version, *, learning=None, use=None, idempotency_key, payload_hash
    ):
        await self._memory_user(user_id)
        return await self._memory_state.pauses(
            user_id, expected_version, learning, use, idempotency_key, payload_hash
        )

    async def read_memory_context(self, user_id, mode_id, turn_id, purpose, query):
        return await self._memory_state.read(
            await self._memory_user(user_id), mode_id, turn_id, purpose, query
        )

    async def inspect_memories(self, user_id, states=None, limit=100, offset=0):
        return await self._memory_state.inspect(
            await self._memory_user(user_id), states, limit, offset
        )

    async def export_memory_data(self, user_id):
        return await self._memory_state.export(await self._memory_user(user_id))

    async def forget_memory(
        self, user_id, memory_id, expected_version, idempotency_key, payload_hash
    ):
        await self._memory_user(user_id)
        return await self._memory_state.forget(
            user_id, memory_id, expected_version, idempotency_key, payload_hash
        )

    async def purge_memory_claims(self):
        return await self._memory_state.purge_claims()

    async def disable_memory(self, user_id, expected_version, idempotency_key, payload_hash):
        await self._memory_user(user_id)
        return await self._memory_state.disable(
            user_id, expected_version, idempotency_key, payload_hash
        )

    async def confirm_forget_all_memory(self, user_id, token, idempotency_key, payload_hash):
        await self._memory_user(user_id)
        return await self._memory_state.forget_all(user_id, token, idempotency_key, payload_hash)

    async def _memory_user(self, user_id):
        user = await self.get_user_by_id(user_id)
        if user is None:
            raise ValueError("Memory owner unavailable")
        return user

    async def get_proactive_consent(self, user_id, scope):
        return await self._proactive_state.get_consent(user_id, scope)

    async def set_proactive_consent(
        self, user_id, scope, policy_version, country_code=None, withdraw=False
    ):
        if not await self.get_user_by_id(user_id):
            raise ValueError("User not found")
        return await self._proactive_state.set_consent(
            user_id, scope, policy_version, country_code, withdraw
        )

    async def set_coaching_consent(self, user_id, policy_version=None):
        return await self.set_proactive_consent(
            user_id, "coaching-v1", policy_version, withdraw=policy_version is None
        )

    async def has_coaching_consent(self, user_id):
        return await self._proactive_state.has_consent(user_id)

    async def reserve_proactive_delivery(
        self, user_id, delivery_key, kind, scheduled_at, program_id=None
    ):
        user = await self.get_user_by_id(user_id)
        if program_id is not None and not await self.get_coaching_program(user_id, program_id):
            raise ValueError("Coaching Program unavailable")
        return await self._proactive_state.reserve(
            user, delivery_key, kind, scheduled_at, program_id
        )

    async def mark_proactive_dispatch(self, user_id, delivery_key):
        user = await self.get_user_by_id(user_id)
        return await self._proactive_state.mark_dispatch(user, delivery_key)

    async def finish_proactive_delivery(self, user_id, delivery_key, outcome):
        return await self._proactive_state.finish_delivery(user_id, delivery_key, outcome)

    async def release_proactive_delivery(self, user_id, delivery_key):
        return await self._proactive_state.release(user_id, delivery_key)

    async def enqueue_coaching_delivery(
        self, user_id, program_id, expected_version, delivery_key, local_day, kind, scheduled_at
    ):
        user = await self.get_user_by_id(user_id)
        if not user:
            return {"status": "unavailable"}
        auth_id = user.get("supabase_auth_id")
        activation = await self.get_activation_state(auth_id) if auth_id else {}
        return await self._proactive_state.enqueue(
            user,
            self._coaching_state.programs,
            self._mode_state.grants.values(),
            program_id,
            expected_version,
            local_day,
            kind,
            scheduled_at,
            delivery_key,
            activated=activation.get("completed") is True,
        )

    async def claim_coaching_deliveries(self, worker_id, limit=25):
        await self._proactive_state.cancel_inactive(self._coaching_state.programs)
        return await self._proactive_state.claim(worker_id, limit)

    async def mark_coaching_dispatch(self, user_id, delivery_key, claim_token):
        user = await self.get_user_by_id(user_id)
        auth_id = user.get("supabase_auth_id") if user else None
        activation = await self.get_activation_state(auth_id) if auth_id else {}
        return await self._proactive_state.dispatch(
            user_id,
            delivery_key,
            claim_token,
            self._coaching_state.programs,
            self._mode_state.grants.values(),
            user=user, activated=activation.get("completed") is True,
            entries=self._coaching_state.entries,
        )

    async def finish_coaching_delivery(self, user_id, delivery_key, claim_token, outcome):
        return await self._proactive_state.finish(
            user_id, delivery_key, claim_token, outcome,
            self._coaching_state.programs, self._coaching_state.entries,
        )

    async def get_coaching_delivery_history(self, user_id, program_id):
        return await self._proactive_state.history(user_id, program_id)

    async def note_coaching_reply(self, user_id, program_id):
        if not await self.get_coaching_program(user_id, program_id):
            return False
        await self._proactive_state.note_reply(user_id, program_id)
        return True

    async def get_coaching_program(
        self, user_id: str, program_id: str | None = None
    ) -> dict | None:
        return await self._coaching_state.get(user_id, program_id)

    async def list_coaching_entries(
        self, user_id: str, program_id: str, limit: int = 20
    ) -> list[dict]:
        return await self._coaching_state.list_entries(user_id, program_id, limit)

    async def draft_coaching_program(
        self,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        *,
        goal: str,
        success_measure: str,
        check_in_days: list[int],
        check_in_time: str,
        timezone: str,
    ) -> dict:
        if not await self.get_user_by_id(user_id):
            raise ValueError("User not found")
        return await self._coaching_state.draft(
            user_id,
            idempotency_key,
            payload_hash,
            goal=goal,
            success_measure=success_measure,
            check_in_days=check_in_days,
            check_in_time=check_in_time,
            timezone=timezone,
        )

    async def change_coaching_program(
        self,
        user_id: str,
        program_id: str,
        expected_version: int,
        action: str,
        idempotency_key: str,
        payload_hash: str,
        *,
        approval_token: str | None = None,
        progress_text: str | None = None,
        weekly_choice: str | None = None,
        extension_days: int | None = None,
    ) -> dict:
        result = await self._coaching_state.change(
            user_id,
            program_id,
            expected_version,
            action,
            idempotency_key,
            payload_hash,
            approval_token=approval_token,
            progress_text=progress_text,
            weekly_choice=weekly_choice,
            extension_days=extension_days,
        )
        await self._proactive_state.cancel_inactive(self._coaching_state.programs)
        return result

    async def revise_coaching_draft(
        self,
        user_id: str,
        program_id: str,
        expected_version: int,
        idempotency_key: str,
        payload_hash: str,
        *,
        goal: str,
        success_measure: str,
        check_in_days: list[int],
        check_in_time: str,
        timezone: str,
    ) -> dict:
        result = await self._coaching_state.revise(
            user_id,
            program_id,
            expected_version,
            idempotency_key,
            payload_hash,
            goal=goal,
            success_measure=success_measure,
            check_in_days=check_in_days,
            check_in_time=check_in_time,
            timezone=timezone,
        )
        await self._proactive_state.cancel_inactive(self._coaching_state.programs)
        return result

    async def issue_coaching_approval(
        self, user_id: str, program_id: str, expected_version: int
    ) -> str:
        return await self._coaching_state.issue_approval(user_id, program_id, expected_version)

    async def confirm_coaching_approval(
        self,
        user_id: str,
        token: str,
        idempotency_key: str,
        payload_hash: str,
    ) -> dict:
        return await self._coaching_state.confirm(user_id, token, idempotency_key, payload_hash)

    async def complete_due_coaching_programs(self) -> list[dict]:
        result = await self._coaching_state.complete_due()
        await self._proactive_state.cancel_inactive(self._coaching_state.programs)
        return result

    async def list_active_coaching_programs(self) -> list[dict]:
        return await self._coaching_state.list_active()

    async def export_coaching_data(self, user_id: str) -> dict:
        return await self._coaching_state.export(user_id)

    async def delete_coaching_data(self, user_id: str, verified_request_id: str) -> None:
        if not verified_request_id or not verified_request_id.strip():
            raise ValueError("Verified deletion required")
        program_ids = [key for key, row in self._coaching_state.programs.items()
                       if row["user_id"] == user_id]
        await self._coaching_state.delete(user_id)
        await self._proactive_state.purge_programs(user_id, program_ids)

    async def get_mode_conversation(self, user_id: str, mode_id: str, channel: str) -> dict | None:
        return await self._mode_state.get_conversation(user_id, mode_id, channel)

    async def get_mode_by_conversation(
        self, user_id: str, channel: str, endpoint: dict
    ) -> str | None:
        return await self._mode_state.mode_by_conversation(user_id, channel, endpoint)

    async def save_mode_conversation(
        self, user_id: str, mode_id: str, channel: str, endpoint: dict, *, alias: bool = False,
    ) -> dict:
        return await self._mode_state.save_conversation(
            self.users.values(), user_id, mode_id, channel, endpoint, alias,
        )

    async def close_mode_conversation(self, user_id: str, mode_id: str, channel: str) -> None:
        await self._mode_state.close_conversation(user_id, mode_id, channel)

    async def list_mode_conversations(self, user_id: str | None = None) -> list[dict]:
        return await self._mode_state.list_conversations(user_id)

    async def claim_handoff_execution(
        self, user_id: str, handoff_id: str, worker_id: str, *,
        execution_session_id: str | None = None,
    ) -> dict:
        return await self._mode_state.claim_execution(
            {row["session_id"]: row for row in self.sessions}, user_id, handoff_id,
            worker_id, execution_session_id,
        )

    async def save_handoff_execution_plan(
        self, user_id: str, handoff_id: str, claim_token: str, plan: list[dict],
    ) -> bool:
        return await self._mode_state.save_execution_plan(user_id, handoff_id, claim_token, plan)

    async def complete_handoff_execution(
        self, user_id: str, handoff_id: str, claim_token: str,
    ) -> bool:
        return await self._mode_state.complete_execution(user_id, handoff_id, claim_token)

    async def fail_handoff_execution(
        self, user_id: str, handoff_id: str, claim_token: str, reason: str,
    ) -> bool:
        return await self._mode_state.fail_execution(user_id, handoff_id, claim_token, reason)

    async def get_handoff_metadata(self, user_id: str, handoff_id: str) -> dict | None:
        return await self._mode_state.handoff_metadata(user_id, handoff_id)

    async def append_handoff_execution_message(
        self, user_id: str, handoff_id: str, claim_token: str, role: str,
        content: str, channel: str,
    ) -> dict | None:
        return await self._mode_state.append_execution_message(
            self.messages, user_id, handoff_id, claim_token, role, content, channel,
        )

    async def claim_handoff_failure_notice(
        self, user_id: str, handoff_id: str, outcome: str = "attempted",
    ) -> bool:
        return await self._mode_state.claim_failure_notice(user_id, handoff_id, outcome)

    async def list_pending_handoff_failure_notices(self, limit: int = 25) -> list[dict]:
        return await self._mode_state.pending_failure_notices(limit)

    async def list_pending_handoff_executions(self, limit: int = 25) -> list[dict]:
        return await self._mode_state.pending_executions(limit)

    async def get_memory_source_message(self, user_id: str, session_id: str) -> dict | None:
        session = next(
            (
                row
                for row in self.sessions
                if row["session_id"] == session_id and row["user_id"] == user_id
            ),
            None,
        )
        if session is None:
            return None
        candidates = [
            row
            for row in self.messages
            if row["session_id"] == session_id
            and row["user_id"] == user_id
            and row["role"] == "user"
        ]
        if not candidates:
            return None
        row = max(candidates, key=lambda item: (item.get("created_at") or "", item["message_id"]))
        return {
            **{
                field: row.get(field)
                for field in (
                    "message_id",
                    "user_id",
                    "session_id",
                    "role",
                    "created_at",
                    "channel",
                )
            },
            "mode_id": session.get("mode_id", "daily"),
        }

    async def count_participant_messages(self, user_id: str) -> int:
        return sum(
            1 for row in self.messages if row["user_id"] == user_id and row["role"] == "user"
        )

    async def get_session_messages(
        self, session_id: str, *, exclude_message_id: str | None = None,
    ) -> list[dict]:
        return [
            {field: row[field] for field in ("role", "content", "created_at")}
            for row in self.messages if row["session_id"] == session_id
            and (exclude_message_id is None or row["message_id"] != exclude_message_id)
        ]

    async def has_session_on_local_day(
        self, user_id: str, timezone: str, mode_id: str = "daily"
    ) -> bool:
        from src.utils import local_day_utc_range
        start_utc, end_utc = local_day_utc_range(timezone)
        for session in self.sessions:
            if session["user_id"] != user_id or session.get("mode_id", "daily") != mode_id:
                continue
            started_at = datetime.fromisoformat(session["started_at"])
            if start_utc <= started_at < end_utc:
                return True
        return False

    async def get_yesterday_summary(
        self, user_id: str, timezone: str, mode_id: str = "daily"
    ) -> str | None:
        from src.utils import local_day_utc_range, yesterday_in_tz
        start_utc, end_utc = local_day_utc_range(timezone, yesterday_in_tz(timezone))
        candidates = []
        for session in self.sessions:
            if (session["user_id"] != user_id or session.get("mode_id", "daily") != mode_id
                or not session.get("context_summary")):
                continue
            started_at = datetime.fromisoformat(session["started_at"])
            if start_utc <= started_at < end_utc:
                candidates.append(session)
        if not candidates:
            return None
        candidates.sort(key=lambda s: s.get("ended_at") or "", reverse=True)
        return candidates[0]["context_summary"]

    async def create_task(self, user_id, title, category="other",
                          session_id=None, suggested_time=None, timezone="UTC"):
        from src.utils import today_in_tz
        today = today_in_tz(timezone).isoformat()
        # Deduplication — mirror MemoryStore behaviour
        for t in self.tasks:
            if (
                t["user_id"] == user_id
                and t["title"] == title
                and t["created_date"] == today
                and t["status"] not in ("completed", "skipped", "cancelled")
            ):
                return t
        task = {
            "task_id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": title,
            "category": category,
            "status": "pending",
            "due_date": today,
            "created_date": today,
            "source_session_id": session_id,
            "suggested_time": suggested_time,
            "deferred_count": 0,
            "actual_completion": None,
            "created_at": utc_now().isoformat(),
            "version": 1,
        }
        self.tasks.append(task)
        return task

    async def get_today_tasks(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        from src.utils import today_in_tz
        today = today_in_tz(timezone).isoformat()
        return [t for t in self.tasks if t["user_id"] == user_id and t.get("due_date") == today]

    async def create_task_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        title: str,
        category: str,
        due_date: str | None,
        session_id: str | None,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        if not any(user["user_id"] == user_id for user in self.users.values()):
            raise ValueError("User not found")
        if session_id:
            session = next(
                (item for item in self.sessions if item["session_id"] == session_id),
                None,
            )
            if not session or session["user_id"] != user_id:
                raise ValueError("Session not found")

        task = {
            "task_id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": title,
            "category": category,
            "status": "pending",
            "due_date": due_date,
            "created_date": utc_now().date().isoformat(),
            "source_session_id": session_id,
            "suggested_time": None,
            "deferred_count": 0,
            "actual_completion": None,
            "created_at": utc_now().isoformat(),
            "version": 1,
        }
        self.tasks.append(task)
        result = {"task": copy.deepcopy(task)}
        self.command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def move_task_planning_day_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        task_id: str,
        due_date: str,
        expected_version: int | None,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])
        if not any(user["user_id"] == user_id for user in self.users.values()):
            raise ValueError("User not found")
        task = next(
            (
                item
                for item in self.tasks
                if item["task_id"] == task_id
                and item["user_id"] == user_id
                and item["status"] == "pending"
            ),
            None,
        )
        if not task:
            raise ValueError("Task not found")
        if expected_version is not None and task.get("version", 1) != expected_version:
            raise StaleVersionError("Task version is stale")
        task["due_date"] = due_date
        task["version"] = task.get("version", 1) + 1
        result = {"task": copy.deepcopy(task)}
        self.command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def get_inbox_tasks(self, user_id: str) -> list[dict]:
        return [
            task
            for task in self.tasks
            if task["user_id"] == user_id
            and task.get("due_date") is None
            and task["status"] == "pending"
        ]

    @reminder_budget_transaction
    async def resolve_task_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        task_id: str,
        outcome: str,
        expected_version: int | None,
        acted_reminder_id: str | None,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        task = next(
            (
                item
                for item in self.tasks
                if item["task_id"] == task_id and item["user_id"] == user_id
            ),
            None,
        )
        if not task:
            raise ValueError("Task not found")
        if acted_reminder_id and not any(
            reminder["reminder_id"] == acted_reminder_id
            and reminder["user_id"] == user_id
            and reminder["task_id"] == task_id
            for reminder in self.reminders
        ):
            raise ValueError("Reminder not found")
        if expected_version is not None and task.get("version", 1) != expected_version:
            raise StaleVersionError("Task version is stale")

        terminal = {"completed", "skipped", "cancelled"}
        transitioned = task["status"] == "pending"
        if task["status"] in terminal and task["status"] != outcome:
            raise InvalidTransitionError("Task is already resolved")

        effects = []
        changed_reminders = []
        if transitioned:
            task["status"] = outcome
            task["version"] = task.get("version", 1) + 1
            task["actual_completion"] = (
                utc_now().isoformat() if outcome == "completed" else None
            )
            active = {"pending", "sending", "sent"}
            for reminder in self.reminders:
                if (
                    reminder["task_id"] != task_id
                    or reminder["user_id"] != user_id
                    or reminder["status"] not in active
                ):
                    continue
                if (
                    reminder["reminder_id"] == acted_reminder_id
                    and reminder["status"] in {"sending", "sent"}
                ):
                    reminder["status"] = "acknowledged"
                else:
                    reminder["status"] = "cancelled"
                reminder["version"] = reminder.get("version", 1) + 1
                changed_reminders.append(copy.deepcopy(reminder))

                effect_key = f"cancel:{reminder['reminder_id']}"
                effect = self.scheduler_outbox.get(effect_key)
                if not effect:
                    effect = {
                        "effect_id": str(uuid.uuid4()),
                        "effect_key": effect_key,
                        "effect_type": "cancel",
                        "user_id": user_id,
                        "task_id": task_id,
                        "reminder_id": reminder["reminder_id"],
                        "payload": {},
                        "status": "pending",
                        "attempts": 0,
                        "worker_id": None,
                        "claimed_at": None,
                        "available_at": utc_now().isoformat(),
                        "completed_at": None,
                        "error_type": None,
                        "created_at": utc_now().isoformat(),
                    }
                    self.scheduler_outbox[effect_key] = effect
                effects.append(
                    {"effect_id": effect["effect_id"], "effect_type": "cancel"}
                )

        result = {
            "task": copy.deepcopy(task),
            "task_version": task.get("version", 1),
            "reminders": changed_reminders,
            "transitioned": transitioned,
            "effect_state": "queued" if effects else "none",
            "effects": effects,
        }
        self.command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def get_yesterday_pending(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        from src.utils import yesterday_in_tz
        yesterday = yesterday_in_tz(timezone).isoformat()
        return [
            t for t in self.tasks
            if t["user_id"] == user_id
            and t["created_date"] == yesterday
            and t["status"] == "pending"
        ]

    async def seed_task_status(self, task_id: str, status: str, user_id: str) -> dict:
        """Fixture-setup status write. See MemoryStore.seed_task_status — resolving a Task
        goes through ResolveTaskCommand, not here."""
        validate_task_status(status)
        for t in self.tasks:
            if t["task_id"] == task_id and t["user_id"] == user_id:
                t["status"] = status
                if status == "completed":
                    t["actual_completion"] = utc_now().isoformat()
                return t
        raise ValueError("Task not found")

    @reminder_budget_transaction
    async def schedule_reminder_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        task_id: str | None,
        replace_reminder_id: str | None,
        scheduled_time: str,
        intended_local_date: str,
        intended_local_time: str,
        intended_timezone: str,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        if replace_reminder_id:
            replaced = next(
                (
                    reminder
                    for reminder in self.reminders
                    if reminder["reminder_id"] == replace_reminder_id
                    and reminder["user_id"] == user_id
                ),
                None,
            )
            if not replaced:
                raise ValueError("Reminder not found")
            task_id = replaced["task_id"]
        task = next(
            (
                item
                for item in self.tasks
                if item["task_id"] == task_id and item["user_id"] == user_id
            ),
            None,
        )
        if not task:
            raise ValueError("Task not found")
        user = next(
            (item for item in self.users.values() if item["user_id"] == user_id),
            None,
        )
        if not user:
            raise ValueError("User not found")

        effects = []
        for reminder in self.reminders:
            if reminder["task_id"] != task_id or reminder["status"] not in {
                "pending",
                "sending",
                "sent",
            }:
                continue
            reminder["status"] = "cancelled"
            reminder["version"] = reminder.get("version", 1) + 1
            effect_key = f"cancel:{reminder['reminder_id']}"
            effect = self.scheduler_outbox.get(effect_key)
            if not effect:
                effect = {
                    "effect_id": str(uuid.uuid4()),
                    "effect_key": effect_key,
                    "effect_type": "cancel",
                    "user_id": user_id,
                    "task_id": task_id,
                    "reminder_id": reminder["reminder_id"],
                    "payload": {},
                    "status": "pending",
                    "attempts": 0,
                    "worker_id": None,
                    "claimed_at": None,
                    "available_at": utc_now().isoformat(),
                    "completed_at": None,
                    "created_at": utc_now().isoformat(),
                }
                self.scheduler_outbox[effect_key] = effect
            effects.append(copy.deepcopy(effect))

        reminder_id = str(uuid.uuid4())
        reminder = {
            "reminder_id": reminder_id,
            "task_id": task_id,
            "user_id": user_id,
            "scheduled_time": scheduled_time,
            "intended_local_date": intended_local_date,
            "intended_local_time": intended_local_time,
            "intended_timezone": intended_timezone,
            "status": "pending",
            "snooze_count": 0,
            "telegram_message_id": None,
            "follow_up_sent": False,
            "evidence_class": "participant",
            "version": 1,
            "created_at": utc_now().isoformat(),
        }
        self.reminders.append(reminder)
        task["due_date"] = intended_local_date
        task["version"] = task.get("version", 1) + 1

        effect_key = f"schedule:{reminder_id}"
        schedule_effect = {
            "effect_id": str(uuid.uuid4()),
            "effect_key": effect_key,
            "effect_type": "schedule",
            "user_id": user_id,
            "task_id": task_id,
            "reminder_id": reminder_id,
            "payload": {
                "scheduled_time": scheduled_time,
                "task_title": task["title"],
            },
            "status": "pending",
            "attempts": 0,
            "worker_id": None,
            "claimed_at": None,
            "available_at": utc_now().isoformat(),
            "completed_at": None,
            "created_at": utc_now().isoformat(),
        }
        self.scheduler_outbox[effect_key] = schedule_effect
        effects.append(copy.deepcopy(schedule_effect))

        result = {
            "reminder": copy.deepcopy(reminder),
            "task_version": task["version"],
            "scheduled_time": scheduled_time,
            "effect_state": "queued",
            "effects": [
                {"effect_id": effect["effect_id"], "effect_type": effect["effect_type"]}
                for effect in effects
            ],
        }
        self.command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    @reminder_budget_transaction
    async def cancel_reminder_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        reminder_id: str,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        reminder = next(
            (
                item
                for item in self.reminders
                if item["reminder_id"] == reminder_id and item["user_id"] == user_id
            ),
            None,
        )
        if not reminder:
            raise ValueError("Reminder not found")
        task = next(
            (
                item
                for item in self.tasks
                if item["task_id"] == reminder["task_id"] and item["user_id"] == user_id
            ),
            None,
        )
        if not task:
            raise ValueError("Reminder not found")

        effect = None
        if reminder["status"] in {"pending", "sending", "sent"}:
            reminder["status"] = "cancelled"
            reminder["version"] = reminder.get("version", 1) + 1
            task["version"] = task.get("version", 1) + 1
            effect_key = f"cancel:{reminder_id}"
            effect = self.scheduler_outbox.get(effect_key)
            if not effect:
                effect = {
                    "effect_id": str(uuid.uuid4()),
                    "effect_key": effect_key,
                    "effect_type": "cancel",
                    "user_id": user_id,
                    "task_id": task["task_id"],
                    "reminder_id": reminder_id,
                    "payload": {},
                    "status": "pending",
                    "attempts": 0,
                    "worker_id": None,
                    "claimed_at": None,
                    "available_at": utc_now().isoformat(),
                    "completed_at": None,
                    "created_at": utc_now().isoformat(),
                }
                self.scheduler_outbox[effect_key] = effect

        result = {
            "reminder": copy.deepcopy(reminder),
            "task_version": task.get("version", 1),
            "effect_state": "queued" if effect else "none",
            "effects": (
                [{"effect_id": effect["effect_id"], "effect_type": "cancel"}]
                if effect
                else []
            ),
        }
        self.command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return result

    async def claim_scheduler_effects(self, limit: int, worker_id: str) -> list[dict]:
        claimed = []
        now = _utc_timestamp(utc_now())
        for effect in sorted(
            self.scheduler_outbox.values(), key=lambda item: _utc_timestamp(item["created_at"])
        ):
            abandoned = (
                effect["status"] == "processing"
                and effect.get("claimed_at")
                and now - _utc_timestamp(effect["claimed_at"]) > timedelta(minutes=5)
            )
            available = _utc_timestamp(effect["available_at"]) <= now
            if (
                (effect["status"] != "pending" or not available)
                and not abandoned
            ) or len(claimed) >= limit:
                continue
            effect["status"] = "processing"
            effect["attempts"] += 1
            effect["worker_id"] = worker_id
            effect["claimed_at"] = now.isoformat()
            claimed.append(copy.deepcopy(effect))
        return claimed

    async def complete_scheduler_effect(
        self,
        effect_id: str,
        user_id: str,
        *,
        succeeded: bool,
        error_type: str | None,
    ) -> None:
        effect = next(
            (
                item
                for item in self.scheduler_outbox.values()
                if item["effect_id"] == effect_id and item["user_id"] == user_id
            ),
            None,
        )
        if not effect:
            raise ValueError("Scheduler effect not found")
        effect["status"] = (
            "completed" if succeeded else ("failed" if effect["attempts"] >= 5 else "pending")
        )
        effect["error_type"] = error_type
        effect["worker_id"] = None
        effect["claimed_at"] = None
        effect["completed_at"] = utc_now().isoformat() if succeeded else None
        effect["available_at"] = utc_now().isoformat()

    @reminder_budget_transaction
    async def create_reminder(self, task_id, user_id, scheduled_time):
        task = next(
            (t for t in self.tasks if t["task_id"] == task_id and t["user_id"] == user_id),
            None,
        )
        if not task:
            raise ValueError("Task not found")

        reminder = {
            "reminder_id": str(uuid.uuid4()),
            "task_id": task_id,
            "user_id": user_id,
            "scheduled_time": scheduled_time,
            "status": "pending",
            "intended_local_date": None,
            "intended_local_time": None,
            "intended_timezone": None,
            "snooze_count": 0,
            "telegram_message_id": None,
            "version": 1,
        }
        self.reminders.append(reminder)
        return reminder

    @reminder_budget_transaction
    async def update_reminder(self, reminder_id: str, updates: dict, user_id: str) -> dict:
        validate_reminder_updates(updates)
        for r in self.reminders:
            if r["reminder_id"] == reminder_id and r["user_id"] == user_id:
                validate_reminder_timing(r, updates)
                r.update(updates)
                return r
        raise ValueError("Reminder not found")

    async def get_pending_reminders(self, user_id: str) -> list[dict]:
        # Mirrors the production `tasks(title, category)` join; the agent's Turn Context reads it.
        results = []
        for reminder in self.reminders:
            if reminder["user_id"] == user_id and reminder["status"] == "pending":
                task = next(
                    (t for t in self.tasks if t["task_id"] == reminder["task_id"]), {}
                )
                results.append(
                    {
                        **reminder,
                        "tasks": {
                            "title": task.get("title", ""),
                            "category": task.get("category", ""),
                        },
                    }
                )
        results.sort(key=lambda item: item["scheduled_time"])
        return results

    async def get_reminder_with_task(self, reminder_id: str, user_id: str) -> dict | None:
        for reminder in self.reminders:
            if reminder["reminder_id"] != reminder_id or reminder["user_id"] != user_id:
                continue
            task = next((t for t in self.tasks if t["task_id"] == reminder["task_id"]), None)
            if not task:
                return {**reminder, "tasks": {"title": "your task", "category": "other"}}
            return {**reminder, "tasks": {"title": task["title"], "category": task["category"]}}
        return None

    async def get_later_context(self, reminder_id: str, user_id: str) -> dict | None:
        reminder = next(
            (
                item
                for item in self.reminders
                if item["reminder_id"] == reminder_id and item["user_id"] == user_id
            ),
            None,
        )
        task = next(
            (
                item
                for item in self.tasks
                if reminder
                and item["task_id"] == reminder["task_id"]
                and item["user_id"] == user_id
            ),
            None,
        )
        user = next(
            (item for item in self.users.values() if item["user_id"] == user_id),
            None,
        )
        if not reminder or not task or not user:
            return None
        return {
            "reminder": copy.deepcopy(reminder),
            "task": copy.deepcopy(task),
            "user": copy.deepcopy(user),
        }

    @reminder_budget_transaction
    async def apply_later_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        reminder_id: str,
        expected_task_version: int | None,
        step: int,
        scheduled_at: str,
        intended_local_date: str,
        intended_local_time: str,
        timezone: str,
        quiet_hours_adjusted: bool,
        task_due_date: str | None,
    ) -> dict:
        receipt_key = (user_id, idempotency_key)
        receipt = self.command_receipts.get(receipt_key)
        if receipt:
            if receipt["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(receipt["result"])

        reminder = next(
            (
                item
                for item in self.reminders
                if item["reminder_id"] == reminder_id and item["user_id"] == user_id
            ),
            None,
        )
        task = next(
            (
                item
                for item in self.tasks
                if reminder
                and item["task_id"] == reminder["task_id"]
                and item["user_id"] == user_id
            ),
            None,
        )
        user = next(
            (item for item in self.users.values() if item["user_id"] == user_id),
            None,
        )
        if not reminder or not task or not user:
            raise ValueError("Reminder not found")
        if reminder["status"] not in {"pending", "sending", "sent"}:
            raise ValueError("Reminder not active")
        if task["status"] != "pending":
            raise ValueError("Task not pending")
        if expected_task_version is not None and task.get("version", 1) != expected_task_version:
            raise StaleVersionError("Task version is stale")
        if step != int(reminder.get("snooze_count", 0)) + 1:
            raise ValueError("Later step is stale")

        result = apply_later_transition(
            user=user,
            task=task,
            reminder=reminder,
            outbox=self.scheduler_outbox,
            new_id=lambda: str(uuid.uuid4()),
            step=step,
            scheduled_at=scheduled_at,
            intended_local_date=intended_local_date,
            intended_local_time=intended_local_time,
            timezone=timezone,
            quiet_hours_adjusted=quiet_hours_adjusted,
            task_due_date=task_due_date,
        )
        self.reminders.append(result["reminder"])
        self.command_receipts[receipt_key] = {
            "payload_hash": payload_hash,
            "result": copy.deepcopy(result),
        }
        return copy.deepcopy(result)

    @reminder_budget_transaction
    async def claim_reminder_for_send(
        self,
        reminder_id: str,
        user_id: str,
        idempotency_key: str,
    ) -> dict | None:
        if any(
            item["idempotency_key"] == idempotency_key
            for item in self.reminder_delivery_attempts.values()
        ):
            return None
        for reminder in self.reminders:
            if (
                reminder["reminder_id"] != reminder_id
                or reminder["user_id"] != user_id
                or reminder["status"] != "pending"
            ):
                continue
            task = next((t for t in self.tasks if t["task_id"] == reminder["task_id"]), None)
            if not task or task["status"] != "pending":
                return None
            now = utc_now().isoformat()
            occurrence = self.reminder_occurrences.setdefault(
                reminder_id,
                {
                    "occurrence_id": str(uuid.uuid4()),
                    "reminder_id": reminder_id,
                    "user_id": user_id,
                    "task_id": reminder["task_id"],
                    "evidence_class": reminder.get("evidence_class", "participant"),
                    "measurable": True,
                    "confirmed_at": reminder.get("created_at", now),
                    "scheduled_for": reminder["scheduled_time"],
                    "first_claimed_at": None,
                    "provider_accepted_at": None,
                    "terminal_at": None,
                    "acknowledged_at": None,
                    "cancelled_at": None,
                },
            )
            attempt_id = str(uuid.uuid4())
            attempt = {
                "attempt_id": attempt_id,
                "occurrence_id": occurrence["occurrence_id"],
                "user_id": user_id,
                "attempt_number": 1
                + sum(
                    item["occurrence_id"] == occurrence["occurrence_id"]
                    for item in self.reminder_delivery_attempts.values()
                ),
                "idempotency_key": idempotency_key,
                "started_at": now,
                "provider_accepted_at": None,
                "finished_at": None,
                "result": None,
                "normalized_cause": None,
                "retry_decision": "unknown",
                "provider_latency_ms": None,
            }
            self.reminder_delivery_attempts[attempt_id] = attempt
            reminder["status"] = "sending"
            occurrence["first_claimed_at"] = occurrence["first_claimed_at"] or now
            return {
                "claimed": True,
                "reminder": copy.deepcopy(reminder),
                "task_status": task["status"],
                "occurrence_id": occurrence["occurrence_id"],
                "attempt": copy.deepcopy(attempt),
            }
        return None

    @reminder_budget_transaction
    async def finish_reminder_delivery(
        self,
        *,
        attempt_id: str,
        reminder_id: str,
        user_id: str,
        result: str,
        normalized_cause: str | None,
        retry_decision: str,
        telegram_message_id: int | None,
        channel: str = "telegram",
        channel_message_ref: str | None = None,
    ) -> dict:
        columns = delivery_columns(
            accepted=result == "accepted", channel=channel,
            telegram_message_id=telegram_message_id, channel_message_ref=channel_message_ref,
        )
        attempt = self.reminder_delivery_attempts[attempt_id]
        reminder = next(item for item in self.reminders if item["reminder_id"] == reminder_id)
        if attempt["user_id"] != user_id or reminder["status"] != "sending":
            raise ValueError("Reminder delivery state conflict")
        finished = utc_now()
        started = datetime.fromisoformat(attempt["started_at"])
        accepted = result == "accepted"
        attempt.update(
            provider_accepted_at=finished.isoformat() if accepted else None,
            finished_at=finished.isoformat(),
            result=result,
            normalized_cause=normalized_cause,
            retry_decision=retry_decision,
            provider_latency_ms=max(0, round((finished - started).total_seconds() * 1000)),
        )
        reminder["status"] = "sent" if accepted else (
            "pending" if retry_decision == "retry" else "failed"
        )
        if columns:
            reminder.update(columns)
        occurrence = self.reminder_occurrences[reminder_id]
        if accepted:
            occurrence["provider_accepted_at"] = (
                occurrence["provider_accepted_at"] or finished.isoformat()
            )
        elif reminder["status"] == "failed":
            occurrence["terminal_at"] = occurrence["terminal_at"] or finished.isoformat()
        return {"attempt": copy.deepcopy(attempt)}

    async def record_scheduler_heartbeat(
        self,
        *,
        owner_key: str,
        worker_id: str,
        missing_jobs: int,
        wrong_time_jobs: int,
        inverse_drift_jobs: int,
    ) -> None:
        now = utc_now().isoformat()
        self.scheduler_runtime = {
            "owner_key": owner_key,
            "worker_id": worker_id,
            "heartbeat_at": now,
            "reconciled_at": now,
            "missing_jobs": missing_jobs,
            "wrong_time_jobs": wrong_time_jobs,
            "inverse_drift_jobs": inverse_drift_jobs,
        }

    async def get_reminder_reliability_health(self) -> dict:
        runtime = self.scheduler_runtime or {}
        pending = [
            effect for effect in self.scheduler_outbox.values() if effect["status"] == "pending"
        ]
        failed = [
            effect for effect in self.scheduler_outbox.values() if effect["status"] == "failed"
        ]
        occurrences = list(self.reminder_occurrences.values())
        attempts = list(self.reminder_delivery_attempts.values())
        oldest_pending_at = min((effect["created_at"] for effect in pending), default=None)
        return {
            "database_checked_at": utc_now().isoformat(),
            "scheduler_heartbeat_at": runtime.get("heartbeat_at"),
            "scheduler_ready": bool(runtime) and (
                utc_now() - datetime.fromisoformat(runtime["heartbeat_at"])
                <= timedelta(minutes=2)
            ),
            "reconciliation_drift": sum(
                runtime.get(key, 0)
                for key in ("missing_jobs", "wrong_time_jobs", "inverse_drift_jobs")
            ),
            "outbox_pending": len(pending),
            "outbox_oldest_pending_at": oldest_pending_at,
            "outbox_oldest_pending_age_ms": (
                _elapsed_ms(utc_now().isoformat(), oldest_pending_at)
                if oldest_pending_at
                else 0
            ),
            "outbox_failed": len(failed),
            "eligible_occurrences": sum(item["measurable"] for item in occurrences),
            "accepted_occurrences": sum(
                item["measurable"] and item["provider_accepted_at"] is not None
                for item in occurrences
            ),
            "reminder_lateness_ms": [
                _elapsed_ms(item["provider_accepted_at"], item["scheduled_for"])
                for item in occurrences
                if item["measurable"] and item["provider_accepted_at"] is not None
            ],
            "scheduler_lag_ms": [
                _elapsed_ms(item["first_claimed_at"], item["scheduled_for"])
                for item in occurrences
                if item["measurable"] and item["first_claimed_at"] is not None
            ],
            "provider_latency_ms": [
                item["provider_latency_ms"]
                for item in attempts
                if item["provider_latency_ms"] is not None
            ],
            "attempt_failures": sum(
                item["result"] in {"rejected", "timeout", "error"} for item in attempts
            ),
            "participant_occurrences": sum(
                item["evidence_class"] == "participant" for item in occurrences
            ),
            "staging_synthetic_occurrences": sum(
                item["evidence_class"] == "staging_synthetic" for item in occurrences
            ),
            "production_synthetic_occurrences": sum(
                item["evidence_class"] == "production_synthetic" for item in occurrences
            ),
        }

    async def get_pending_reminders_for_reload(self, cutoff: datetime) -> list[dict]:
        rows = []
        for reminder in self.reminders:
            scheduled = datetime.fromisoformat(reminder["scheduled_time"])
            if reminder["status"] != "pending" or scheduled < cutoff:
                continue
            task = next((t for t in self.tasks if t["task_id"] == reminder["task_id"]), None)
            user = next(
                (u for u in self.users.values() if u["user_id"] == reminder["user_id"]),
                None,
            )
            rows.append({
                **reminder,
                "tasks": {"title": task["title"] if task else "your task"},
                "user_profiles": {
                    "primary_channel": user.get("primary_channel", "telegram") if user else None,
                },
                "reminder_occurrences": (
                    {
                        "occurrence_id": self.reminder_occurrences[
                            reminder["reminder_id"]
                        ]["occurrence_id"],
                        "reminder_delivery_attempts": [
                            copy.deepcopy(attempt)
                            for attempt in self.reminder_delivery_attempts.values()
                            if attempt["occurrence_id"]
                            == self.reminder_occurrences[reminder["reminder_id"]][
                                "occurrence_id"
                            ]
                        ],
                    }
                    if reminder["reminder_id"] in self.reminder_occurrences
                    else None
                ),
            })
        return rows

    async def get_reminders_for_reconciliation(self) -> list[dict]:
        rows = []
        for reminder in self.reminders:
            if reminder["status"] not in {"pending", "sending", "sent"}:
                continue
            task = next((t for t in self.tasks if t["task_id"] == reminder["task_id"]), None)
            user = next(
                (u for u in self.users.values() if u["user_id"] == reminder["user_id"]),
                None,
            )
            rows.append({
                **reminder,
                "tasks": (
                    {
                        "title": task["title"],
                        "status": task["status"],
                        "user_id": task["user_id"],
                    }
                    if task
                    else None
                ),
                "user_profiles": {
                    "primary_channel": user.get("primary_channel", "telegram") if user else None,
                },
                "reminder_occurrences": (
                    {
                        "occurrence_id": self.reminder_occurrences[
                            reminder["reminder_id"]
                        ]["occurrence_id"],
                        "reminder_delivery_attempts": [
                            copy.deepcopy(attempt)
                            for attempt in self.reminder_delivery_attempts.values()
                            if attempt["occurrence_id"]
                            == self.reminder_occurrences[reminder["reminder_id"]][
                                "occurrence_id"
                            ]
                        ],
                    }
                    if reminder["reminder_id"] in self.reminder_occurrences
                    else None
                ),
            })
        return rows

    @reminder_budget_transaction
    async def acknowledge_reminders_for_task(self, task_id: str, user_id: str) -> list[str]:
        ids = []
        for r in self.reminders:
            if r["task_id"] == task_id and r["user_id"] == user_id and r["status"] == "pending":
                r["status"] = "acknowledged"
                ids.append(r["reminder_id"])
        return ids

    async def save_feedback(self, user_id, content, session_id=None):
        fb = {"user_id": user_id, "content": content, "session_id": session_id}
        self.feedback.append(fb)
        return fb

    async def log_usage(self, user_id, model, input_tokens, output_tokens, session_id=None):
        self.usage.append({
            "user_id": user_id, "model": model,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
        })

    # ── Pairing and Account Linking ──

    async def get_user_by_auth_id(self, auth_id: str) -> dict | None:
        """Find user profile linked to a Supabase auth.uid()."""
        for user in self.users.values():
            if user.get("supabase_auth_id") == auth_id:
                return dict(user)
        return None

    async def get_dashboard_snapshot(self, user_id: str) -> dict:
        from src.dashboard_snapshot import build_dashboard_snapshot

        user = next((item for item in self.users.values() if item["user_id"] == user_id), None)
        if not user:
            raise ValueError("User not found")
        activation = (
            await self.get_activation_state(user["supabase_auth_id"])
            if user.get("supabase_auth_id")
            else None
        )
        return build_dashboard_snapshot(
            user,
            [item for item in self.tasks if item["user_id"] == user_id],
            [item for item in self.reminders if item["user_id"] == user_id],
            [item for item in self.sessions if item["user_id"] == user_id],
            activation=activation,
        )

    async def create_pairing_token(self, token: str, auth_id: str, expires_at: datetime) -> dict:
        """Create a new pairing token linked to a Supabase auth.uid()."""
        journey = self.activation_journeys.get(auth_id)
        if not journey or not journey.get("acknowledged_at"):
            raise ActivationTermsRequiredError
        now = utc_now()
        window_start = now - PAIRING_TOKEN_WINDOW
        recent_count = sum(
            1
            for row in self.pairing_tokens.values()
            if row["supabase_auth_id"] == auth_id
            and datetime.fromisoformat(row["created_at"]) >= window_start
        )
        if recent_count >= PAIRING_TOKEN_LIMIT:
            raise PairingTokenRateLimitError

        for existing in self.pairing_tokens.values():
            if existing["supabase_auth_id"] == auth_id and not existing["consumed"]:
                existing["invalidated_at"] = now.isoformat()

        row = {
            "token": token,
            "supabase_auth_id": auth_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "consumed": False,
            "invalidated_at": None,
        }
        self.pairing_tokens[token] = row
        return dict(row)

    async def complete_pairing(self, token: str, chat_id: int) -> dict:
        """Atomically consume a token and link identities without reassignment."""
        return await self.complete_channel_pairing(token, "telegram", str(chat_id))

    async def get_pairing_token_owner(self, token: str) -> str | None:
        """The auth id behind a usable Pairing token, without consuming it."""
        return live_token_owner(self.pairing_tokens, token)

    async def complete_channel_pairing(self, token: str, channel: str, external_id: str) -> dict:
        """Link a messaging app to the token's account; mirrors `complete_pairing_v2`."""
        return self._identity_state.complete_pairing(
            users=self.users.values(), tokens=self.pairing_tokens, token=token,
            channel=channel, external_id=external_id, insert_user=self._insert_user,
        )

    # ── Dashboard-first Activation Journey ──

    async def get_activation_state(self, auth_id: str) -> dict:
        users = {user["user_id"]: user for user in self.users.values()}
        tasks = {task["task_id"]: task for task in self.tasks}
        reminders = {reminder["reminder_id"]: reminder for reminder in self.reminders}
        return activation_state(
            journeys=self.activation_journeys,
            users=users,
            pairing_tokens=self.pairing_tokens,
            tasks=tasks,
            reminders=reminders,
            occurrences=self.reminder_occurrences,
            auth_id=auth_id,
            now=utc_now(),
        )

    async def acknowledge_activation_terms(self, auth_id: str, policy_version: str) -> dict:
        return acknowledge_terms(
            self.activation_journeys,
            auth_id=auth_id,
            policy_version=policy_version,
            now=utc_now(),
        )

    async def update_activation_profile(
        self,
        auth_id: str,
        *,
        name: str,
        timezone: str,
        wake_time: str,
        sleep_time: str,
    ) -> dict:
        users = {user["user_id"]: user for user in self.users.values()}
        return update_profile(
            self.activation_journeys,
            users,
            auth_id=auth_id,
            name=name,
            timezone=timezone,
            wake_time=wake_time,
            sleep_time=sleep_time,
            now=utc_now(),
        )

    @reminder_budget_transaction
    async def create_activation_test_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        title: str,
        retry: bool,
        scheduled_time: str,
        intended_local_date: str,
        intended_local_time: str,
        intended_timezone: str,
    ) -> dict:
        users = {user["user_id"]: user for user in self.users.values()}
        tasks = {task["task_id"]: task for task in self.tasks}
        reminders = {reminder["reminder_id"]: reminder for reminder in self.reminders}
        previous_task_ids = set(tasks)
        previous_reminder_ids = set(reminders)
        result = create_test(
            journeys=self.activation_journeys,
            users=users,
            tasks=tasks,
            reminders=reminders,
            occurrences=self.reminder_occurrences,
            receipts=self.command_receipts,
            outbox=self.scheduler_outbox,
            user_id=user_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            title=title,
            retry=retry,
            scheduled_time=scheduled_time,
            intended_local_date=intended_local_date,
            intended_local_time=intended_local_time,
            intended_timezone=intended_timezone,
            now=utc_now(),
        )
        self.tasks.extend(tasks[key] for key in tasks.keys() - previous_task_ids)
        self.reminders.extend(
            reminders[key] for key in reminders.keys() - previous_reminder_ids
        )
        return result

    # Content-free confirmed Mode suggestions; trusted application callers only.
    async def _suggestions(self):
        from src.memory.suggestions import LocalSuggestionState

        if not hasattr(self, "_suggestion_state"):
            self._suggestion_state = LocalSuggestionState(self)
        return self._suggestion_state

    async def get_mode_suggestion_preference(self, user_id):
        return await (await self._suggestions()).preference(user_id)

    async def set_mode_suggestion_preference(self, user_id, enabled):
        return await (await self._suggestions()).set_preference(user_id, enabled)

    async def create_mode_suggestion(self, user_id, session_id, target_mode_id,
                                     *, grant_required=True):
        return await (await self._suggestions()).create(
            user_id, session_id, target_mode_id, grant_required=grant_required
        )

    async def get_mode_suggestion(self, user_id, offer_id):
        return await (await self._suggestions()).get(user_id, offer_id)

    async def claim_mode_suggestion_opening(self, user_id, offer_id):
        return await (await self._suggestions()).claim_opening(user_id, offer_id)

    async def release_mode_suggestion_opening(self, user_id, offer_id, claim_token):
        return await (await self._suggestions()).release_opening(user_id, offer_id, claim_token)

    async def complete_mode_suggestion_opening(self, user_id, offer_id, claim_token):
        return await (await self._suggestions()).complete_opening(user_id, offer_id, claim_token)

    async def resolve_mode_suggestion(self, user_id, offer_id, confirm):
        return await (await self._suggestions()).resolve(user_id, offer_id, confirm)



class FakeDB:
    """Minimal fake for self.store.db.table(...) chains used by SessionManager."""

    def __init__(self, store: FakeStore):
        self._store = store

    def table(self, name: str):
        return FakeTable(self._store, name)


class FakeTable:
    """Chainable fake for Supabase table queries."""

    def __init__(self, store: FakeStore, table_name: str):
        self._store = store
        self._table = table_name
        self._filters: dict = {}
        self._select_cols = "*"
        self._limit_n = None

    def select(self, cols):
        self._select_cols = cols
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def gte(self, col, val):
        self._filters[f"{col}__gte"] = val
        return self

    def lt(self, col, val):
        self._filters[f"{col}__lt"] = val
        return self

    def is_(self, col, val):
        self._filters[f"{col}__is"] = val
        return self

    def in_(self, col, vals):
        self._filters[f"{col}__in"] = vals
        return self

    def not_(self):
        return self

    def order(self, col, desc=False):
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def maybe_single(self):
        return self

    def single(self):
        return self

    def execute(self):
        """Return matching rows from the in-memory store."""
        if self._table == "sessions":
            data = self._filter_list(self._store.sessions)
        elif self._table == "tasks":
            data = self._filter_list(self._store.tasks)
        elif self._table == "reminders":
            data = self._filter_list(self._store.reminders)
        else:
            data = []

        if self._limit_n:
            data = data[:self._limit_n]

        return FakeResult(data)

    def update(self, updates):
        return self

    def insert(self, data):
        return self

    def _filter_list(self, items: list[dict]) -> list[dict]:
        result = []
        for item in items:
            match = True
            for key, val in self._filters.items():
                if "__gte" in key:
                    col = key.replace("__gte", "")
                    if item.get(col, "") < val:
                        match = False
                elif "__lt" in key:
                    col = key.replace("__lt", "")
                    if item.get(col, "") >= val:
                        match = False
                elif "__is" in key:
                    col = key.replace("__is", "")
                    if val == "null" and item.get(col) is not None:
                        match = False
                elif "__in" in key:
                    col = key.replace("__in", "")
                    if item.get(col) not in val:
                        match = False
                else:
                    if item.get(key) != val:
                        match = False
            if match:
                result.append(item)
        return result


class FakeResult:
    def __init__(self, data):
        if isinstance(data, list) and len(data) == 0:
            self.data = []
        elif isinstance(data, list):
            self.data = data
        else:
            self.data = data


class FakeScheduler:
    """Fake reminder scheduler. Records schedule/cancel calls."""

    def __init__(self):
        self.scheduled: list[dict] = []
        self.cancelled: list[str] = []

    def schedule_reminder(self, user_id, reminder_id, send_time, chat_id, task_title):
        self.scheduled.append({
            "user_id": user_id, "reminder_id": reminder_id,
            "send_time": send_time, "chat_id": chat_id, "task_title": task_title,
        })

    def cancel_reminder(self, user_id, reminder_id):
        self.cancelled.append(reminder_id)
