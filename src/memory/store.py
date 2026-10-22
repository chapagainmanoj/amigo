"""Supabase CRUD operations for all entities."""

import json
import logging
from datetime import UTC, datetime
from functools import wraps
from time import perf_counter

from src.commands.base import (
    IdempotencyConflictError,
    InvalidTransitionError,
    PairingChangedError,
    ProactiveBudgetExceeded,
    StaleVersionError,
)
from src.memory.modes import ModeGrant, ModeGrantResult, ModeResult
from src.memory.pairing import ActivationTermsRequiredError, PairingTokenRateLimitError
from src.memory.reminders import validate_reminder_timing, validate_reminder_updates
from src.memory.tasks import validate_task_status
from src.schema import require_schema_version
from src.utils import local_day_utc_range, today_in_tz, utc_now, yesterday_in_tz

logger = logging.getLogger(__name__)


def _observe_database_call(method):
    """Log content-free Store latency and outcome for staging/load evidence."""

    @wraps(method)
    async def observed(*args, **kwargs):
        started = perf_counter()
        outcome = "error"
        try:
            result = await method(*args, **kwargs)
            outcome = "ok"
            return result
        finally:
            logger.info(
                "database_operation=%s outcome=%s duration_ms=%.3f",
                method.__name__,
                outcome,
                (perf_counter() - started) * 1000,
            )

    return observed


def _raise_command_error(error: Exception) -> None:
    message = str(error)
    if "proactive_budget_exhausted" in message:
        raise ProactiveBudgetExceeded("The shared daily message budget is full") from None
    if "immutable_reminder_schedule" in message:
        raise ValueError("Reminder timing is immutable; use the reschedule command") from None
    if "coaching_stale_version" in message:
        raise StaleVersionError("Coaching Program version changed") from None
    if "coaching_invalid_transition" in message or "coaching_approval_required" in message:
        raise InvalidTransitionError(
            "Coaching action or participant approval unavailable"
        ) from None
    if "coaching_program_unavailable" in message or "invalid_coaching_" in message:
        raise ValueError("Coaching Program input or owner unavailable") from None
    if "verified_deletion_required" in message:
        raise ValueError("Verified deletion required") from None
    if "idempotency_key_conflict" in message:
        raise IdempotencyConflictError("Idempotency key was reused with different input") from None
    if "task_not_found" in message:
        raise ValueError("Task not found") from None
    if "reminder_not_found" in message:
        raise ValueError("Reminder not found") from None
    if "reminder_not_active" in message:
        raise ValueError("Reminder not found") from None
    if "task_not_pending" in message:
        raise ValueError("Task not found") from None
    if "user_not_found" in message:
        raise ValueError("User not found") from None
    if "stale_task_version" in message:
        raise StaleVersionError("Task version is stale") from None
    if "task_already_resolved" in message:
        raise InvalidTransitionError("Task is already resolved") from None
    if "later_step_stale" in message:
        raise StaleVersionError("Later action is stale") from None


class MemoryStore:
    """All Supabase read/write operations in one place."""

    def __init__(self):
        self.db = None

    @_observe_database_call
    async def connect(self) -> None:
        """Initialize the shared native-async Supabase client before serving work."""
        from src.db.supabase import get_supabase

        self.db = await get_supabase()

    @_observe_database_call
    async def verify_schema_version(self, expected: int) -> int:
        """Require the exact migration-chain marker before startup side effects."""
        result = await self.db.rpc("get_app_schema_version").execute()
        return require_schema_version(result.data, expected)

    @_observe_database_call
    async def get_command_receipt(self, user_id: str, idempotency_key: str) -> dict | None:
        result = await (self.db.table("command_receipts").select("payload_hash, result")
                        .eq("user_id", user_id).eq("idempotency_key", idempotency_key)
                        .maybe_single().execute())
        return result.data if result and result.data else None

    # ── User Profiles ──

    @_observe_database_call
    async def get_user_by_id(self, user_id: str) -> dict | None:
        result = await (self.db.table("user_profiles").select("*").eq("user_id", user_id)
                        .maybe_single().execute())
        return result.data if result and result.data else None

    @_observe_database_call
    async def get_user_by_chat_id(self, chat_id: int) -> dict | None:
        """Find user by Telegram chat ID. Returns None if not onboarded."""
        result = await (
            self.db.table("user_profiles")
            .select("*")
            .eq("telegram_chat_id", chat_id)
            .maybe_single()
            .execute()
        )
        return result.data if result and result.data else None

    @_observe_database_call
    async def create_user(self, chat_id: int) -> dict:
        """Create a new user profile during onboarding."""
        result = await (
            self.db.table("user_profiles")
            .insert({"telegram_chat_id": chat_id})
            .execute()
        )
        return result.data[0]

    @_observe_database_call
    async def update_user(self, user_id: str, updates: dict) -> dict:
        """Update user profile fields."""
        updates["updated_at"] = utc_now().isoformat()
        result = await (
            self.db.table("user_profiles")
            .update(updates)
            .eq("user_id", user_id)
            .execute()
        )
        return result.data[0]

    # ── Telegram Update Claims ──

    @_observe_database_call
    async def claim_telegram_update(
        self, update_id: int, chat_id: int, update_kind: str
    ) -> dict:
        """Atomically reserve one Telegram update for its first delivery."""
        result = await self.db.rpc(
            "claim_telegram_update",
            {
                "p_update_id": update_id,
                "p_telegram_chat_id": chat_id,
                "p_update_kind": update_kind,
            },
        ).execute()
        return result.data

    @_observe_database_call
    async def finish_telegram_update(
        self,
        update_id: int,
        *,
        status: str,
        failure_code: str | None = None,
    ) -> dict:
        """Record a claimed update's terminal status without retaining message content."""
        result = await self.db.rpc(
            "finish_telegram_update",
            {
                "p_update_id": update_id,
                "p_status": status,
                "p_failure_code": failure_code,
            },
        ).execute()
        return result.data

    # ── Sessions ──

    @_observe_database_call
    async def get_active_session(self, user_id: str, mode_id: str = "daily") -> dict | None:
        """Get the current open session (ended_at is NULL)."""
        result = await (
            self.db.table("sessions")
            .select("*")
            .eq("user_id", user_id)
            .eq("mode_id", mode_id)
            .is_("ended_at", "null")
            .order("started_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    @_observe_database_call
    async def create_session(
        self, user_id: str, session_type: str = "casual", mode_id: str = "daily"
    ) -> dict:
        """Start a new session."""
        result = await (
            self.db.table("sessions")
            .insert({
                "user_id": user_id,
                "session_type": session_type,
                "mode_id": mode_id,
                "active_mode_id": None if mode_id == "daily" else mode_id,
            })
            .execute()
        )
        return result.data[0]

    @_observe_database_call
    async def close_session(self, session_id: str, summary: str | None = None) -> None:
        """Close a session with optional context summary."""
        await self.db.table("sessions").update({
            "ended_at": utc_now().isoformat(),
            "context_summary": summary,
        }).eq("session_id", session_id).execute()

    @_observe_database_call
    async def touch_session(self, session_id: str) -> None:
        """Update last_activity_at and increment message_count."""
        # Note: message_count increment is approximate; fine for Phase 1a
        session = await (
            self.db.table("sessions")
            .select("message_count")
            .eq("session_id", session_id)
            .single()
            .execute()
        )
        await self.db.table("sessions").update({
            "last_activity_at": utc_now().isoformat(),
            "message_count": (session.data["message_count"] or 0) + 1,
        }).eq("session_id", session_id).execute()

    # ── Session Modes, trial grants, and confirmed handoffs ──

    @_observe_database_call
    async def get_active_mode(self, user_id: str, session_id: str) -> str | None:
        result = await (
            self.db.table("sessions").select("active_mode_id")
            .eq("user_id", user_id).eq("session_id", session_id)
            .is_("ended_at", "null").maybe_single().execute()
        )
        return result.data.get("active_mode_id") if result and result.data else None

    @_observe_database_call
    async def set_active_mode(
        self, user_id: str, session_id: str, mode_id: str | None, *, grant_required: bool = True,
    ) -> ModeResult:
        """Atomically check grant + owned open Session; flags come from trusted registry code."""
        result = await self.db.rpc("set_active_mode", {
            "p_user_id": user_id, "p_session_id": session_id, "p_mode_id": mode_id,
            "p_grant_required": grant_required,
        }).execute()
        return result.data

    @_observe_database_call
    async def grant_mode(
        self, user_id: str, mode_id: str, operator: str, reason: str,
        expires_at: datetime | None = None,
    ) -> ModeGrantResult:
        params = {"p_user_id": user_id, "p_mode_id": mode_id,
                  "p_operator": operator, "p_reason": reason}
        if expires_at is not None:
            expiry = expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at
            params["p_expires_at"] = expiry.isoformat()
        # Omitting expiry uses the SQL default; sending JSON null would be an invalid grant.
        result = await self.db.rpc("grant_mode", params).execute()
        return result.data

    @_observe_database_call
    async def revoke_mode_grant(
        self, user_id: str, mode_id: str, operator: str, reason: str,
    ) -> ModeGrantResult:
        result = await self.db.rpc("revoke_mode_grant", {
            "p_user_id": user_id, "p_mode_id": mode_id,
            "p_operator": operator, "p_reason": reason,
        }).execute()
        return result.data

    @_observe_database_call
    async def get_active_mode_grant(self, user_id: str, mode_id: str) -> ModeGrant | None:
        result = await (
            self.db.table("mode_grants").select("*").eq("user_id", user_id)
            .eq("mode_id", mode_id).is_("revoked_at", "null")
            .gt("expires_at", utc_now().replace(tzinfo=UTC).isoformat())
            .maybe_single().execute()
        )
        return result.data if result and result.data else None

    @_observe_database_call
    async def create_handoff(
        self, user_id: str, session_id: str, source_mode_id: str, target_mode_id: str,
        carried_request: str, *, source_grant_required: bool = True,
        target_grant_required: bool = True,
    ) -> ModeResult:
        """Trusted adapter checks live registry/declared target before invoking this Store API."""
        result = await self.db.rpc("create_mode_handoff", {
            "p_user_id": user_id, "p_session_id": session_id,
            "p_source_mode_id": source_mode_id, "p_target_mode_id": target_mode_id,
            "p_carried_request": carried_request,
            "p_source_grant_required": source_grant_required,
            "p_target_grant_required": target_grant_required,
        }).execute()
        return result.data

    @_observe_database_call
    async def resolve_handoff(
        self, user_id: str, session_id: str, handoff_id: str, confirm: bool,
    ) -> ModeResult:
        """Resolve only; the Store never executes a callback's carried request."""
        result = await self.db.rpc("resolve_mode_handoff", {
            "p_user_id": user_id, "p_session_id": session_id,
            "p_handoff_id": handoff_id, "p_confirm": confirm,
        }).execute()
        return result.data

    # ── Messages ──

    @_observe_database_call
    async def add_message(
        self, session_id: str, user_id: str, role: str, content: str, channel: str = "telegram"
    ) -> dict:
        """Store a conversation message."""
        result = await (
            self.db.table("messages")
            .insert({
                "session_id": session_id,
                "user_id": user_id,
                "role": role,
                "content": content,
                "channel": channel,
            })
            .execute()
        )
        return result.data[0]

    async def _coaching_rpc(self, name: str, params: dict) -> object:
        try:
            result = await self.db.rpc(name, params).execute()
        except Exception as error:
            _raise_command_error(error)
            raise
        return result.data

    async def _memory_rpc(self, name, params):
        try:
            return await self._coaching_rpc(name, params)
        except (IdempotencyConflictError, StaleVersionError, InvalidTransitionError):
            raise
        except Exception as error:
            message = str(error)
            if "stale version" in message:
                raise StaleVersionError("Memory version changed") from None
            if "invalid transition" in message:
                raise InvalidTransitionError("Memory confirmation or action unavailable") from None
            if "idempotency key reused" in message:
                raise IdempotencyConflictError("Memory command key was reused") from None
            if "Memory" in message or "memory" in message:
                raise ValueError("Memory input or owner unavailable") from None
            raise

    async def get_memory_settings(self, user_id):
        return await self._memory_rpc(
            "memory_command",
            {
                "p_user_id": user_id,
                "p_operation": "get_memory_settings",
                "p_args": {},
            },
        )

    async def prepare_memory_confirmation(
        self,
        user_id,
        operation,
        preview_digest,
        expected_settings_version,
        memory_id=None,
        expected_memory_version=None,
    ):
        return await self._memory_rpc(
            "memory_command",
            {
                "p_user_id": user_id,
                "p_operation": "prepare_memory_confirmation",
                "p_args": {
                    "operation": operation,
                    "preview_digest": preview_digest,
                    "expected_settings_version": expected_settings_version,
                    "memory_id": memory_id,
                    "expected_memory_version": expected_memory_version,
                },
            },
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
        return await self._memory_rpc(
            "memory_command",
            {
                "p_user_id": user_id,
                "p_operation": "confirm_memory_save",
                "p_args": {
                    "token": token,
                    "payload": payload,
                    "idempotency_key": idempotency_key,
                    "payload_hash": payload_hash,
                    "enable_memory": enable_memory,
                    "policy_version": policy_version,
                },
            },
        )

    async def transition_memory(
        self, user_id, memory_id, expected_version, action, idempotency_key, payload_hash
    ):
        return await self._memory_rpc(
            "memory_command",
            {
                "p_user_id": user_id,
                "p_operation": "transition_memory",
                "p_args": {
                    "memory_id": memory_id,
                    "expected_version": expected_version,
                    "action": action,
                    "idempotency_key": idempotency_key,
                    "payload_hash": payload_hash,
                },
            },
        )

    async def set_memory_pauses(
        self, user_id, expected_version, *, learning=None, use=None, idempotency_key, payload_hash
    ):
        return await self._memory_rpc(
            "memory_command",
            {
                "p_user_id": user_id,
                "p_operation": "set_memory_pauses",
                "p_args": {
                    "expected_version": expected_version,
                    "learning": learning,
                    "use": use,
                    "idempotency_key": idempotency_key,
                    "payload_hash": payload_hash,
                },
            },
        )

    async def read_memory_context(self, user_id, mode_id, turn_id, purpose, query):
        return await self._memory_rpc(
            "memory_command",
            {
                "p_user_id": user_id,
                "p_operation": "read_memory_context",
                "p_args": {
                    "mode_id": mode_id,
                    "turn_id": turn_id,
                    "purpose": purpose,
                    "query": query,
                },
            },
        )

    async def inspect_memories(self, user_id, states=None, limit=100, offset=0):
        return await self._memory_rpc(
            "memory_command",
            {
                "p_user_id": user_id,
                "p_operation": "inspect_memories",
                "p_args": {"states": states, "limit": limit, "offset": offset},
            },
        )

    async def export_memory_data(self, user_id):
        return await self._memory_rpc(
            "memory_command",
            {
                "p_user_id": user_id,
                "p_operation": "export_memory_data",
                "p_args": {},
            },
        )

    async def forget_memory(
        self, user_id, memory_id, expected_version, idempotency_key, payload_hash
    ):
        return await self._memory_rpc(
            "memory_command",
            {
                "p_user_id": user_id,
                "p_operation": "forget_memory",
                "p_args": {
                    "memory_id": memory_id,
                    "expected_version": expected_version,
                    "idempotency_key": idempotency_key,
                    "payload_hash": payload_hash,
                },
            },
        )

    async def confirm_forget_all_memory(self, user_id, token, idempotency_key, payload_hash):
        return await self._memory_rpc(
            "memory_command",
            {
                "p_user_id": user_id,
                "p_operation": "confirm_forget_all_memory",
                "p_args": {
                    "token": token,
                    "idempotency_key": idempotency_key,
                    "payload_hash": payload_hash,
                },
            },
        )

    async def get_proactive_consent(self, user_id, scope):
        return await self._coaching_rpc(
            "get_proactive_consent", {"p_user_id": user_id, "p_scope": scope}
        )

    async def set_proactive_consent(
        self, user_id, scope, policy_version, country_code=None, withdraw=False
    ):
        return await self._coaching_rpc(
            "set_proactive_consent",
            dict(
                p_user_id=user_id,
                p_scope=scope,
                p_policy_version=policy_version,
                p_country_code=country_code,
                p_withdraw=withdraw,
            ),
        )

    async def set_coaching_consent(self, user_id, policy_version=None):
        return await self._coaching_rpc(
            "set_coaching_consent", dict(p_user_id=user_id, p_policy_version=policy_version)
        )

    async def has_coaching_consent(self, user_id):
        return await self._coaching_rpc("has_coaching_consent", {"p_user_id": user_id})

    async def reserve_proactive_delivery(
        self, user_id, delivery_key, kind, scheduled_at, program_id=None
    ):
        value = scheduled_at.isoformat() if hasattr(scheduled_at, "isoformat") else scheduled_at
        return await self._coaching_rpc(
            "reserve_proactive_delivery",
            dict(
                p_user_id=user_id,
                p_delivery_key=delivery_key,
                p_kind=kind,
                p_scheduled_at=value,
                p_program_id=program_id,
            ),
        )

    async def release_proactive_delivery(self, user_id, delivery_key):
        return await self._coaching_rpc(
            "release_proactive_delivery", dict(p_user_id=user_id, p_delivery_key=delivery_key)
        )

    async def enqueue_coaching_delivery(
        self, user_id, program_id, expected_version, delivery_key, local_day, kind, scheduled_at
    ):
        value = scheduled_at.isoformat() if hasattr(scheduled_at, "isoformat") else scheduled_at
        return await self._coaching_rpc(
            "enqueue_coaching_delivery",
            dict(
                p_user_id=user_id,
                p_program_id=program_id,
                p_expected_version=expected_version,
                p_delivery_key=delivery_key,
                p_local_day=local_day,
                p_kind=kind,
                p_scheduled_at=value,
            ),
        )

    async def claim_coaching_deliveries(self, worker_id, limit=25):
        return await self._coaching_rpc(
            "claim_coaching_deliveries", dict(p_worker_id=worker_id, p_limit=limit)
        )

    async def mark_coaching_dispatch(self, user_id, delivery_key, claim_token):
        return await self._coaching_rpc(
            "mark_coaching_dispatch",
            dict(
                p_user_id=user_id,
                p_delivery_key=delivery_key,
                p_claim_token=claim_token,
            ),
        )

    async def finish_coaching_delivery(self, user_id, delivery_key, claim_token, outcome):
        return await self._coaching_rpc(
            "finish_coaching_delivery",
            dict(
                p_user_id=user_id,
                p_delivery_key=delivery_key,
                p_claim_token=claim_token,
                p_outcome=outcome,
            ),
        )

    async def get_coaching_delivery_history(self, user_id, program_id):
        return await self._coaching_rpc(
            "get_coaching_delivery_history", dict(p_user_id=user_id, p_program_id=program_id)
        )

    async def note_coaching_reply(self, user_id, program_id):
        return await self._coaching_rpc(
            "note_coaching_reply", dict(p_user_id=user_id, p_program_id=program_id)
        )

    @_observe_database_call
    async def get_coaching_program(
        self, user_id: str, program_id: str | None = None
    ) -> dict | None:
        query = self.db.table("coaching_programs").select("*").eq("user_id", user_id)
        query = (
            query.eq("program_id", program_id)
            if program_id is not None
            else query.in_("state", ["draft", "active", "paused"])
        )
        result = await query.maybe_single().execute()
        return result.data if result and result.data else None

    @_observe_database_call
    async def list_coaching_entries(
        self, user_id: str, program_id: str, limit: int = 20
    ) -> list[dict]:
        if not await self.get_coaching_program(user_id, program_id):
            raise ValueError("Coaching Program unavailable")
        result = await (
            self.db.table("coaching_entries")
            .select("*")
            .eq("user_id", user_id)
            .eq("program_id", program_id)
            .order("created_at", desc=True)
            .limit(max(1, min(limit, 100)))
            .execute()
        )
        return list(reversed(result.data or []))

    @_observe_database_call
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
        return await self._coaching_rpc(
            "coaching_program_command",
            {
                "p_user_id": user_id,
                "p_program_id": None,
                "p_expected_version": None,
                "p_action": "draft",
                "p_idempotency_key": idempotency_key,
                "p_payload_hash": payload_hash,
                "p_data": {
                    "goal": goal,
                    "success_measure": success_measure,
                    "check_in_days": check_in_days,
                    "check_in_time": check_in_time,
                    "timezone": timezone,
                },
            },
        )

    @_observe_database_call
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
        return await self._coaching_rpc(
            "coaching_program_command",
            {
                "p_user_id": user_id,
                "p_program_id": program_id,
                "p_expected_version": expected_version,
                "p_action": action,
                "p_idempotency_key": idempotency_key,
                "p_payload_hash": payload_hash,
                "p_data": {
                    "approval_token": approval_token,
                    "progress_text": progress_text,
                    "weekly_choice": weekly_choice,
                    "extension_days": extension_days,
                },
            },
        )

    @_observe_database_call
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
        return await self._coaching_rpc(
            "coaching_program_command",
            {
                "p_user_id": user_id,
                "p_program_id": program_id,
                "p_expected_version": expected_version,
                "p_action": "revise",
                "p_idempotency_key": idempotency_key,
                "p_payload_hash": payload_hash,
                "p_data": {
                    "goal": goal,
                    "success_measure": success_measure,
                    "check_in_days": check_in_days,
                    "check_in_time": check_in_time,
                    "timezone": timezone,
                },
            },
        )

    @_observe_database_call
    async def issue_coaching_approval(
        self, user_id: str, program_id: str, expected_version: int
    ) -> str:
        return await self._coaching_rpc(
            "issue_coaching_approval",
            {
                "p_user_id": user_id,
                "p_program_id": program_id,
                "p_expected_version": expected_version,
            },
        )

    @_observe_database_call
    async def confirm_coaching_approval(
        self,
        user_id: str,
        token: str,
        idempotency_key: str,
        payload_hash: str,
    ) -> dict:
        return await self._coaching_rpc(
            "confirm_coaching_approval",
            {
                "p_user_id": user_id,
                "p_token": token,
                "p_idempotency_key": idempotency_key,
                "p_payload_hash": payload_hash,
            },
        )

    @_observe_database_call
    async def complete_due_coaching_programs(self) -> list[dict]:
        return await self._coaching_rpc("complete_due_coaching_programs", {}) or []

    @_observe_database_call
    async def list_active_coaching_programs(self) -> list[dict]:
        result = await (
            self.db.table("coaching_programs")
            .select("*")
            .eq("state", "active")
            .gt("ends_at", utc_now().isoformat())
            .execute()
        )
        return result.data or []

    @_observe_database_call
    async def export_coaching_data(self, user_id: str) -> dict:
        return await self._coaching_rpc("export_coaching_data", {"p_user_id": user_id})

    @_observe_database_call
    async def delete_coaching_data(self, user_id: str, verified_request_id: str) -> None:
        await self._coaching_rpc(
            "delete_coaching_data",
            {
                "p_user_id": user_id,
                "p_verified_request_id": verified_request_id,
            },
        )

    @_observe_database_call
    async def get_mode_conversation(self, user_id: str, mode_id: str, channel: str) -> dict | None:
        result = await (self.db.table("mode_conversations").select("*").eq("user_id", user_id)
                        .eq("mode_id", mode_id).eq("channel", channel).is_("closed_at", "null")
                        .maybe_single().execute())
        return result.data if result and result.data else None

    @_observe_database_call
    async def get_mode_by_conversation(
        self, user_id: str, channel: str, endpoint: dict
    ) -> str | None:
        result = await (self.db.table("mode_conversation_endpoints").select("mode_id")
                        .eq("user_id", user_id).eq("channel", channel)
                        .eq("endpoint", json.dumps(endpoint, sort_keys=True, allow_nan=False))
                        .maybe_single().execute())
        return result.data["mode_id"] if result and result.data else None

    @_observe_database_call
    async def save_mode_conversation(
        self, user_id: str, mode_id: str, channel: str, endpoint: dict, *, alias: bool = False,
    ) -> dict:
        result = await self.db.rpc("save_mode_conversation", {
            "p_user_id": user_id, "p_mode_id": mode_id, "p_channel": channel,
            "p_endpoint": endpoint, "p_alias": alias,
        }).execute()
        return result.data

    @_observe_database_call
    async def close_mode_conversation(self, user_id: str, mode_id: str, channel: str) -> None:
        await self.db.rpc("close_mode_conversation", {
            "p_user_id": user_id, "p_mode_id": mode_id, "p_channel": channel,
        }).execute()

    @_observe_database_call
    async def list_mode_conversations(self, user_id: str | None = None) -> list[dict]:
        query = self.db.table("mode_conversations").select("*")
        if user_id is not None:
            query = query.eq("user_id", user_id)
        result = await query.execute()
        return result.data or []

    @_observe_database_call
    async def claim_handoff_execution(
        self, user_id: str, handoff_id: str, worker_id: str, *,
        execution_session_id: str | None = None,
    ) -> dict:
        result = await self.db.rpc("claim_handoff_execution", {
            "p_user_id": user_id, "p_handoff_id": handoff_id, "p_worker_id": worker_id,
            "p_execution_session_id": execution_session_id,
        }).execute()
        return result.data

    @_observe_database_call
    async def save_handoff_execution_plan(
        self, user_id: str, handoff_id: str, claim_token: str, plan: list[dict],
    ) -> bool:
        result = await self.db.rpc("save_handoff_execution_plan", {
            "p_user_id": user_id, "p_handoff_id": handoff_id,
            "p_claim_token": claim_token, "p_plan": plan,
        }).execute()
        return bool(result.data)

    @_observe_database_call
    async def complete_handoff_execution(
        self, user_id: str, handoff_id: str, claim_token: str,
    ) -> bool:
        result = await self.db.rpc("complete_handoff_execution", {
            "p_user_id": user_id, "p_handoff_id": handoff_id, "p_claim_token": claim_token,
        }).execute()
        return bool(result.data)

    @_observe_database_call
    async def list_pending_handoff_executions(self, limit: int = 25) -> list[dict]:
        result = await self.db.rpc("list_pending_handoff_executions", {"p_limit": limit}).execute()
        return result.data or []

    @_observe_database_call
    async def get_memory_source_message(self, user_id: str, session_id: str) -> dict | None:
        """Latest owned user Message metadata; transcript reads keep their existing DTO."""
        result = await (
            self.db.table("messages")
            .select(
                "message_id,user_id,session_id,role,created_at,channel,sessions!inner(user_id,mode_id)"
            )
            .eq("user_id", user_id)
            .eq("session_id", session_id)
            .eq("role", "user")
            .eq("sessions.user_id", user_id)
            .order("created_at", desc=True)
            .order("message_id", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        session = row.get("sessions")
        if (
            row.get("user_id") != user_id
            or not isinstance(session, dict)
            or session.get("user_id") != user_id
        ):
            return None
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

    @_observe_database_call
    async def get_session_messages(self, session_id: str) -> list[dict]:
        """Get all messages in a session, ordered by time."""
        result = await (
            self.db.table("messages")
            .select("role, content, created_at")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
        )
        return result.data

    @_observe_database_call
    async def has_session_on_local_day(
        self, user_id: str, timezone: str, mode_id: str = "daily"
    ) -> bool:
        """Return whether the user has any session that started today locally."""
        start_utc, end_utc = local_day_utc_range(timezone)
        result = await (
            self.db.table("sessions")
            .select("session_id")
            .eq("user_id", user_id)
            .eq("mode_id", mode_id)
            .gte("started_at", start_utc.isoformat())
            .lt("started_at", end_utc.isoformat())
            .limit(1)
            .execute()
        )
        return bool(result.data)

    @_observe_database_call
    async def get_yesterday_summary(
        self, user_id: str, timezone: str, mode_id: str = "daily"
    ) -> str | None:
        """Get the most recent closed session summary from yesterday locally."""
        yesterday = yesterday_in_tz(timezone)
        start_utc, end_utc = local_day_utc_range(timezone, yesterday)
        result = await (
            self.db.table("sessions")
            .select("context_summary")
            .eq("user_id", user_id)
            .eq("mode_id", mode_id)
            .gte("started_at", start_utc.isoformat())
            .lt("started_at", end_utc.isoformat())
            .not_.is_("context_summary", "null")
            .order("ended_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return result.data["context_summary"]
        return None

    # ── Tasks ──

    @_observe_database_call
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
        """Atomically create an Inbox/planned Task and persist its command receipt."""
        try:
            result = await self.db.rpc(
                "create_task_command",
                {
                    "p_user_id": user_id,
                    "p_idempotency_key": idempotency_key,
                    "p_payload_hash": payload_hash,
                    "p_title": title,
                    "p_category": category,
                    "p_due_date": due_date,
                    "p_source_session_id": session_id,
                },
            ).execute()
        except Exception as error:
            if "idempotency_key_conflict" in str(error):
                raise IdempotencyConflictError(
                    "Idempotency key was reused with different input"
                ) from None
            if "user_not_found" in str(error):
                raise ValueError("User not found") from None
            if "session_not_found" in str(error):
                raise ValueError("Session not found") from None
            raise
        return result.data

    @_observe_database_call
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
        """Atomically move one owned pending Task and persist its command receipt."""
        try:
            result = await self.db.rpc(
                "move_task_planning_day_command",
                {
                    "p_user_id": user_id,
                    "p_idempotency_key": idempotency_key,
                    "p_payload_hash": payload_hash,
                    "p_task_id": task_id,
                    "p_due_date": due_date,
                    "p_expected_version": expected_version,
                },
            ).execute()
        except Exception as error:
            _raise_command_error(error)
            raise
        return result.data

    @_observe_database_call
    async def get_inbox_tasks(self, user_id: str) -> list[dict]:
        result = await (
            self.db.table("tasks")
            .select("*")
            .eq("user_id", user_id)
            .is_("due_date", "null")
            .eq("status", "pending")
            .order("created_at")
            .execute()
        )
        return result.data

    @_observe_database_call
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
        """Atomically resolve a Task, its active Reminders, receipt, and cancel effects."""
        try:
            result = await self.db.rpc(
                "resolve_task_command",
                {
                    "p_user_id": user_id,
                    "p_idempotency_key": idempotency_key,
                    "p_payload_hash": payload_hash,
                    "p_task_id": task_id,
                    "p_outcome": outcome,
                    "p_expected_version": expected_version,
                    "p_acted_reminder_id": acted_reminder_id,
                },
            ).execute()
        except Exception as error:
            _raise_command_error(error)
            raise
        return result.data

    @_observe_database_call
    async def create_task(self, user_id: str, title: str, category: str = "other",
                          session_id: str | None = None,
                          suggested_time: str | None = None,
                          timezone: str = "UTC") -> dict:
        """Create a new task. Sets created_date in user's timezone.

        Idempotent: if a non-done task with the same title already exists today
        for this user, returns the existing row instead of creating a duplicate.
        This guards against the LLM calling create_task twice in the same turn.
        """
        today = today_in_tz(timezone).isoformat()
        existing = await (
            self.db.table("tasks")
            .select("*")
            .eq("user_id", user_id)
            .eq("title", title)
            .eq("created_date", today)
            .not_.in_("status", ["completed", "skipped", "cancelled"])
            .maybe_single()
            .execute()
        )
        if existing and existing.data:
            logger.info("Deduplicating create_task — returning existing task '%s'", title)
            return existing.data

        data = {
            "user_id": user_id,
            "title": title,
            "category": category,
            "source_session_id": session_id,
            "created_date": today,
            "due_date": today,
        }
        if suggested_time:
            data["suggested_time"] = suggested_time
        result = await self.db.table("tasks").insert(data).execute()
        return result.data[0]

    @_observe_database_call
    async def get_today_tasks(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        """Get Tasks assigned to today's planning day in the user's timezone."""
        today = today_in_tz(timezone).isoformat()
        result = await (
            self.db.table("tasks")
            .select("*")
            .eq("user_id", user_id)
            .eq("due_date", today)
            .order("created_at")
            .execute()
        )
        return result.data

    @_observe_database_call
    async def get_yesterday_pending(self, user_id: str, timezone: str = "UTC") -> list[dict]:
        """Get yesterday's incomplete tasks (in user's timezone)."""
        yesterday = yesterday_in_tz(timezone).isoformat()
        result = await (
            self.db.table("tasks")
            .select("*")
            .eq("user_id", user_id)
            .eq("created_date", yesterday)
            .eq("status", "pending")
            .execute()
        )
        return result.data

    @_observe_database_call
    async def seed_task_status(self, task_id: str, status: str, user_id: str) -> dict:
        """Put a Task into a starting state for a fixture. Never resolves one.

        A bare UPDATE: no Reminder cancellation, no terminal monotonicity, no outbox cancel
        effects — so a Task marked terminal here keeps firing reminders, and a terminal Task can
        be dragged back to pending.

        Resolving a Task goes through ResolveTaskCommand, which calls migration 007's
        resolve_task_command and does all three (issue 06). Named `seed_` so nothing reaches for
        it by mistake; test_resolve_task_command.py fails the build if production code calls it.
        """
        validate_task_status(status)
        updates: dict = {"status": status}
        if status == "completed":
            updates["actual_completion"] = utc_now().isoformat()
        result = await (
            self.db.table("tasks")
            .update(updates)
            .eq("task_id", task_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not result.data:
            raise ValueError("Task not found")
        return result.data[0]

    # ── Reminders ──

    @_observe_database_call
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
        try:
            result = await self.db.rpc(
                "schedule_reminder_command",
                {
                    "p_user_id": user_id,
                    "p_idempotency_key": idempotency_key,
                    "p_payload_hash": payload_hash,
                    "p_task_id": task_id,
                    "p_replace_reminder_id": replace_reminder_id,
                    "p_scheduled_time": scheduled_time,
                    "p_intended_local_date": intended_local_date,
                    "p_intended_local_time": intended_local_time,
                    "p_intended_timezone": intended_timezone,
                },
            ).execute()
        except Exception as error:
            _raise_command_error(error)
            raise
        return result.data

    @_observe_database_call
    async def cancel_reminder_command(
        self,
        *,
        user_id: str,
        idempotency_key: str,
        payload_hash: str,
        reminder_id: str,
    ) -> dict:
        try:
            result = await self.db.rpc(
                "cancel_reminder_command",
                {
                    "p_user_id": user_id,
                    "p_idempotency_key": idempotency_key,
                    "p_payload_hash": payload_hash,
                    "p_reminder_id": reminder_id,
                },
            ).execute()
        except Exception as error:
            _raise_command_error(error)
            raise
        return result.data

    @_observe_database_call
    async def claim_scheduler_effects(self, limit: int, worker_id: str) -> list[dict]:
        """Delegate UTC-instant availability, lease expiry and ordering to the TIMESTAMPTZ RPC."""
        result = await self.db.rpc(
            "claim_scheduler_outbox",
            {"p_limit": limit, "p_worker_id": worker_id},
        ).execute()
        return result.data or []

    @_observe_database_call
    async def complete_scheduler_effect(
        self,
        effect_id: str,
        user_id: str,
        *,
        succeeded: bool,
        error_type: str | None,
    ) -> None:
        await self.db.rpc(
            "complete_scheduler_outbox",
            {
                "p_effect_id": effect_id,
                "p_user_id": user_id,
                "p_succeeded": succeeded,
                "p_error_type": error_type,
            },
        ).execute()

    @_observe_database_call
    async def create_reminder(self, task_id: str, user_id: str,
                              scheduled_time: str) -> dict:
        """Schedule a reminder for a task."""
        task = await (
            self.db.table("tasks")
            .select("task_id")
            .eq("task_id", task_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not task or not task.data:
            raise ValueError("Task not found")

        try:
            result = await (
                self.db.table("reminders")
                .insert({
                    "task_id": task_id,
                    "user_id": user_id,
                    "scheduled_time": scheduled_time,
                })
                .execute()
            )
        except Exception as error:
            _raise_command_error(error)
            raise
        return result.data[0]

    @_observe_database_call
    async def update_reminder(self, reminder_id: str, updates: dict, user_id: str) -> dict:
        """Update reminder fields (status, snooze_count, telegram_message_id)."""
        validate_reminder_updates(updates)
        if "scheduled_time" in updates:
            existing = await (self.db.table("reminders").select("scheduled_time")
                              .eq("reminder_id", reminder_id).eq("user_id", user_id)
                              .maybe_single().execute())
            if not existing or not existing.data:
                raise ValueError("Reminder not found")
            validate_reminder_timing(existing.data, updates)
        try:
            result = await (
                self.db.table("reminders")
                .update(updates)
                .eq("reminder_id", reminder_id)
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as error:
            _raise_command_error(error)
            raise
        if not result.data:
            raise ValueError("Reminder not found")
        return result.data[0]

    @_observe_database_call
    async def get_pending_reminders(self, user_id: str) -> list[dict]:
        """Get all pending reminders for a user."""
        result = await (
            self.db.table("reminders")
            .select("*, tasks(title, category)")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .order("scheduled_time")
            .execute()
        )
        return result.data

    @_observe_database_call
    async def get_reminder_with_task(self, reminder_id: str, user_id: str) -> dict | None:
        """Fetch a reminder with task title/category for callback handling."""
        result = await (
            self.db.table("reminders")
            .select("*, tasks(title, category)")
            .eq("reminder_id", reminder_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        return result.data if result and result.data else None

    @_observe_database_call
    async def get_later_context(self, reminder_id: str, user_id: str) -> dict | None:
        """Load the owned Reminder, Task, and timing preferences needed by LaterPolicy."""
        result = await (
            self.db.table("reminders")
            .select(
                "*, tasks(*), "
                "user_profiles!reminders_user_id_fkey("
                "user_id, telegram_chat_id, timezone, wake_time, sleep_time)"
            )
            .eq("reminder_id", reminder_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not result or not result.data:
            return None
        row = dict(result.data)
        task = row.pop("tasks")
        user = row.pop("user_profiles")
        return {"reminder": row, "task": task, "user": user}

    @_observe_database_call
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
        """Atomically acknowledge a Reminder and create its Later replacement."""
        try:
            result = await self.db.rpc(
                "apply_later_command",
                {
                    "p_user_id": user_id,
                    "p_idempotency_key": idempotency_key,
                    "p_payload_hash": payload_hash,
                    "p_reminder_id": reminder_id,
                    "p_expected_task_version": expected_task_version,
                    "p_step": step,
                    "p_scheduled_time": scheduled_at,
                    "p_intended_local_date": intended_local_date,
                    "p_intended_local_time": intended_local_time,
                    "p_intended_timezone": timezone,
                    "p_quiet_hours_adjusted": quiet_hours_adjusted,
                    "p_task_due_date": task_due_date,
                },
            ).execute()
        except Exception as error:
            _raise_command_error(error)
            raise
        return result.data

    @_observe_database_call
    async def claim_reminder_for_send(
        self,
        reminder_id: str,
        user_id: str,
        idempotency_key: str,
    ) -> dict | None:
        """Atomically claim a delivery and create its immutable attempt row."""
        result = await self.db.rpc(
            "claim_reminder_delivery",
            {
                "p_reminder_id": reminder_id,
                "p_user_id": user_id,
                "p_idempotency_key": idempotency_key,
            },
        ).execute()
        return result.data if result.data.get("claimed") else None

    @_observe_database_call
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
    ) -> dict:
        """Finish one delivery attempt and transition its Reminder atomically."""
        response = await self.db.rpc(
            "finish_reminder_delivery",
            {
                "p_attempt_id": attempt_id,
                "p_reminder_id": reminder_id,
                "p_user_id": user_id,
                "p_result": result,
                "p_normalized_cause": normalized_cause,
                "p_retry_decision": retry_decision,
                "p_telegram_message_id": telegram_message_id,
            },
        ).execute()
        return response.data

    @_observe_database_call
    async def record_scheduler_heartbeat(
        self,
        *,
        owner_key: str,
        worker_id: str,
        missing_jobs: int,
        wrong_time_jobs: int,
        inverse_drift_jobs: int,
    ) -> None:
        """Persist scheduler liveness and the latest content-free drift counts."""
        await self.db.rpc(
            "record_scheduler_heartbeat",
            {
                "p_owner_key": owner_key,
                "p_worker_id": worker_id,
                "p_missing_jobs": missing_jobs,
                "p_wrong_time_jobs": wrong_time_jobs,
                "p_inverse_drift_jobs": inverse_drift_jobs,
            },
        ).execute()

    @_observe_database_call
    async def get_reminder_reliability_health(self) -> dict:
        """Return content-free Reminder, scheduler, and outbox reliability evidence."""
        result = await self.db.rpc("get_reminder_reliability_health", {}).execute()
        return result.data

    @_observe_database_call
    async def get_pending_reminders_for_reload(self, cutoff: datetime) -> list[dict]:
        """Get pending reminders due after cutoff with task title and chat id."""
        result = await (
            self.db.table("reminders")
            .select("*, tasks(title), user_profiles!reminders_user_id_fkey(telegram_chat_id)")
            .eq("status", "pending")
            .gte("scheduled_time", cutoff.isoformat())
            .execute()
        )
        return result.data

    @_observe_database_call
    async def get_reminders_for_reconciliation(self) -> list[dict]:
        """Return authoritative active Reminder rows and their owned delivery context."""
        result = await (
            self.db.table("reminders")
            .select(
                "*, tasks(title, status, user_id), "
                "user_profiles!reminders_user_id_fkey(telegram_chat_id), "
                "reminder_occurrences(occurrence_id, "
                "reminder_delivery_attempts(attempt_id, attempt_number, finished_at))"
            )
            .in_("status", ["pending", "sending", "sent"])
            .execute()
        )
        return result.data

    @_observe_database_call
    async def acknowledge_reminders_for_task(self, task_id: str, user_id: str) -> list[str]:
        """Mark all pending reminders for a task as acknowledged.

        Returns list of reminder_ids so caller can cancel APScheduler jobs.
        """
        result = await (
            self.db.table("reminders")
            .select("reminder_id")
            .eq("task_id", task_id)
            .eq("user_id", user_id)
            .eq("status", "pending")
            .execute()
        )
        reminder_ids = [r["reminder_id"] for r in result.data]

        if reminder_ids:
            (
                await self.db.table("reminders")
                .update({"status": "acknowledged"})
                .eq("task_id", task_id)
                .eq("user_id", user_id)
                .eq("status", "pending")
                .execute()
            )

        return reminder_ids

    # ── Feedback ──

    @_observe_database_call
    async def save_feedback(self, user_id: str, content: str,
                            session_id: str | None = None) -> dict:
        """Store user feedback from /feedback command."""
        result = await (
            self.db.table("feedback")
            .insert({
                "user_id": user_id,
                "content": content,
                "session_id": session_id,
            })
            .execute()
        )
        return result.data[0]

    # ── Usage Events ──

    @_observe_database_call
    async def log_usage(self, user_id: str, model: str, input_tokens: int,
                        output_tokens: int, session_id: str | None = None) -> None:
        """Log LLM usage for cost tracking."""
        # Rough cost estimation (Gemini Flash pricing)
        cost_per_m_input = 0.15
        cost_per_m_output = 0.60
        estimated_cost = (
            (input_tokens / 1_000_000) * cost_per_m_input
            + (output_tokens / 1_000_000) * cost_per_m_output
        )
        await self.db.table("usage_events").insert({
            "user_id": user_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimated_cost,
            "session_id": session_id,
        }).execute()

    # ── Pairing and Account Linking ──

    @_observe_database_call
    async def get_user_by_auth_id(self, auth_id: str) -> dict | None:
        """Find user profile linked to a Supabase auth.uid()."""
        result = await (
            self.db.table("user_profiles")
            .select("*")
            .eq("supabase_auth_id", auth_id)
            .maybe_single()
            .execute()
        )
        return result.data if result else None

    @_observe_database_call
    async def get_dashboard_snapshot(self, user_id: str) -> dict:
        """Return one transactionally consistent dashboard read model."""
        result = await self.db.rpc("get_dashboard_snapshot", {"p_user_id": user_id}).execute()
        return result.data

    @_observe_database_call
    async def create_pairing_token(self, token: str, auth_id: str, expires_at: datetime) -> dict:
        """Atomically issue a rate-limited token and invalidate older tokens."""
        try:
            result = await self.db.rpc(
                "issue_pairing_token",
                {
                    "p_token": token,
                    "p_auth_id": auth_id,
                    "p_expires_at": expires_at.isoformat(),
                },
            ).execute()
        except Exception as exc:
            if "pairing_token_rate_limited" in str(exc):
                raise PairingTokenRateLimitError from None
            if "activation_not_acknowledged" in str(exc):
                raise ActivationTermsRequiredError from None
            raise

        data = result.data
        return data[0] if isinstance(data, list) else data

    @_observe_database_call
    async def complete_pairing(self, token: str, chat_id: int) -> dict:
        """Atomically consume a token and link identities without reassignment."""
        result = await self.db.rpc(
            "complete_pairing",
            {"p_token": token, "p_telegram_chat_id": chat_id},
        ).execute()
        return result.data

    # ── Dashboard-first Activation Journey ──

    @_observe_database_call
    async def get_activation_state(self, auth_id: str) -> dict:
        """Refresh and return one canonical Activation Journey snapshot."""
        result = await self.db.rpc(
            "get_activation_state",
            {"p_auth_id": auth_id},
        ).execute()
        return result.data

    @_observe_database_call
    async def acknowledge_activation_terms(self, auth_id: str, policy_version: str) -> dict:
        """Persist the verified Dashboard Account's policy acknowledgement."""
        result = await self.db.rpc(
            "acknowledge_activation_terms",
            {"p_auth_id": auth_id, "p_policy_version": policy_version},
        ).execute()
        return result.data

    @_observe_database_call
    async def update_activation_profile(
        self,
        auth_id: str,
        *,
        name: str,
        timezone: str,
        wake_time: str,
        sleep_time: str,
    ) -> dict:
        """Atomically update the paired profile and journey progress."""
        try:
            result = await self.db.rpc(
                "update_activation_profile",
                {
                    "p_auth_id": auth_id,
                    "p_name": name,
                    "p_timezone": timezone,
                    "p_wake_time": wake_time,
                    "p_sleep_time": sleep_time,
                },
            ).execute()
        except Exception as error:
            if "activation_not_acknowledged" in str(error):
                raise ValueError("Activation limits must be acknowledged first") from None
            if "activation_not_paired" in str(error):
                raise ValueError("Telegram must be paired first") from None
            raise
        return result.data

    @_observe_database_call
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
        """Atomically create or retry the private Activation test Reminder."""
        try:
            result = await self.db.rpc(
                "create_activation_test_command",
                {
                    "p_user_id": user_id,
                    "p_idempotency_key": idempotency_key,
                    "p_payload_hash": payload_hash,
                    "p_title": title,
                    "p_retry": retry,
                    "p_scheduled_time": scheduled_time,
                    "p_intended_local_date": intended_local_date,
                    "p_intended_local_time": intended_local_time,
                    "p_intended_timezone": intended_timezone,
                },
            ).execute()
        except Exception as error:
            _raise_command_error(error)
            message = str(error)
            if "activation_pairing_changed" in message:
                raise PairingChangedError(
                    "Telegram Pairing completed while this request was in flight; retry it"
                ) from None
            if "activation_profile_incomplete" in message:
                raise ValueError("Activation profile must be completed first") from None
            if "activation_test_exists" in message:
                raise ValueError("Activation test Reminder already exists") from None
            if "activation_retry_not_allowed" in message:
                raise ValueError("Activation test Reminder is not eligible for retry") from None
            if "activation_timezone_mismatch" in message:
                raise ValueError(
                    "Test Reminder timezone must match the Activation profile"
                ) from None
            raise
        return result.data

    async def get_mode_suggestion_preference(self, user_id):
        return await self._coaching_rpc("get_mode_suggestion_preference", {"p_user_id": user_id})

    async def set_mode_suggestion_preference(self, user_id, enabled):
        return await self._coaching_rpc("set_mode_suggestion_preference", {
            "p_user_id": user_id, "p_enabled": enabled,
        })

    async def create_mode_suggestion(self, user_id, session_id, target_mode_id,
                                     *, grant_required=True):
        if not isinstance(grant_required, bool):
            raise ValueError("Grant requirement must be Boolean")
        return await self._coaching_rpc("create_mode_suggestion", {
            "p_user_id": user_id, "p_session_id": session_id,
            "p_target_mode_id": target_mode_id, "p_grant_required": grant_required,
        })

    async def get_mode_suggestion(self, user_id, offer_id):
        return await self._coaching_rpc("get_mode_suggestion", {
            "p_user_id": user_id, "p_offer_id": offer_id,
        })

    async def resolve_mode_suggestion(self, user_id, offer_id, confirm):
        if not isinstance(confirm, bool):
            return None
        return await self._coaching_rpc("resolve_mode_suggestion", {
            "p_user_id": user_id, "p_offer_id": offer_id, "p_confirm": confirm,
        })
