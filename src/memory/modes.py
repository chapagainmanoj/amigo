"""Mode Store DTOs and atomic local mirrors of migration 016's RPC semantics.

Registry/live checks and participant confirmation belong to trusted application adapters.
This module never authorizes model arguments, executes a carried request, or queries Supabase.
"""

import asyncio
import copy
import json
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, NotRequired, TypedDict

from src.utils import utc_now

MODE_GRANT_TTL = timedelta(days=14)
MODE_HANDOFF_TTL = timedelta(minutes=10)
MODE_GRANT_CAP = 5


class ModeGrant(TypedDict):
    grant_id: str
    user_id: str
    mode_id: str
    granted_at: str
    expires_at: str
    revoked_at: str | None
    granted_by: str
    reason: str


class ModeGrantResult(TypedDict):
    status: Literal["invalid", "granted", "already_active", "cap_reached", "revoked", "not_active"]
    grant: NotRequired[ModeGrant]


class ModeHandoff(TypedDict):
    handoff_id: str
    user_id: str
    session_id: str
    source_mode_id: str
    target_mode_id: str
    source_grant_required: bool
    target_grant_required: bool
    carried_request: str
    created_at: str
    expires_at: str
    resolved_at: str | None
    resolution: Literal["confirmed", "declined", "expired", "unavailable"] | None
    execution_claimed_at: str | None
    execution_claim_token: str | None
    execution_worker_id: str | None
    execution_session_id: str | None
    execution_clock_at: str | None
    execution_attempts: int
    executed_at: str | None
    execution_failed_at: str | None
    execution_failure_reason: str | None
    execution_plan: list[dict]


class ModeResult(TypedDict):
    status: Literal["invalid", "unavailable", "set", "pending", "confirmed", "declined", "expired"]
    handoff: NotRequired[ModeHandoff]


def _json_identity(value: object) -> str:
    """Match JSONB equality without conflating booleans with numbers."""
    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if type(value) is float and value.is_integer():
            return int(Decimal(str(value)))
        return value

    return json.dumps(normalize(value), sort_keys=True, allow_nan=False)


async def _valid_mode(value: str | None) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value) is not None


async def _time(value: str | datetime) -> datetime:
    instant = datetime.fromisoformat(value) if isinstance(value, str) else value
    return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant.astimezone(UTC)


class LocalModeState:
    """Serialized local transitions; returned rows are detached from authoritative state."""

    def __init__(self):
        self.grants: dict[str, ModeGrant] = {}
        self.events: list[dict] = []
        self.handoffs: dict[str, ModeHandoff] = {}
        self.conversations: dict[tuple[str, str, str], dict] = {}
        self.endpoints: dict[tuple[str, str], dict] = {}
        self.lock = asyncio.Lock()

    async def _event(self, grant: ModeGrant, action: str, operator: str, reason: str) -> None:
        self.events.append(
            {
                "event_id": str(uuid.uuid4()),
                "grant_id": grant["grant_id"],
                "user_id": grant["user_id"],
                "mode_id": grant["mode_id"],
                "action": action,
                "operator": operator,
                "reason": reason,
                "occurred_at": (await _time(utc_now())).isoformat(),
            }
        )

    async def _active_grant(self, user_id: str, mode_id: str, now: datetime) -> ModeGrant | None:
        for row in self.grants.values():
            if (
                row["user_id"] == user_id
                and row["mode_id"] == mode_id
                and row["revoked_at"] is None
                and await _time(row["expires_at"]) > now
            ):
                return row
        return None

    async def get_active_grant(self, user_id: str, mode_id: str) -> ModeGrant | None:
        async with self.lock:
            return copy.deepcopy(await self._active_grant(user_id, mode_id, await _time(utc_now())))

    async def grant(
        self,
        users: Iterable[dict],
        user_id: str,
        mode_id: str,
        operator: str,
        reason: str,
        expires_at: datetime | None,
    ) -> ModeGrantResult:
        started = await _time(utc_now())
        expiry = started + MODE_GRANT_TTL if expires_at is None else await _time(expires_at)
        if (
            not await _valid_mode(mode_id)
            or mode_id == "daily"
            or not operator
            or not operator.strip()
            or not reason
            or not reason.strip()
            or not started < expiry <= started + MODE_GRANT_TTL
        ):
            return {"status": "invalid"}
        async with self.lock:
            now = await _time(utc_now())
            if not any(user["user_id"] == user_id for user in users) or expiry <= now:
                return {"status": "invalid"}
            for row in self.grants.values():
                if (
                    row["mode_id"] == mode_id
                    and row["revoked_at"] is None
                    and await _time(row["expires_at"]) <= now
                ):
                    row["revoked_at"] = now.isoformat()
                    await self._event(
                        row, "expired", operator, "Expiry observed while granting: " + reason
                    )
            existing = await self._active_grant(user_id, mode_id, now)
            if existing:
                return {"status": "already_active", "grant": copy.deepcopy(existing)}
            if (
                sum(
                    row["mode_id"] == mode_id and row["revoked_at"] is None
                    for row in self.grants.values()
                )
                >= MODE_GRANT_CAP
            ):
                return {"status": "cap_reached"}
            row = ModeGrant(
                grant_id=str(uuid.uuid4()),
                user_id=user_id,
                mode_id=mode_id,
                granted_at=now.isoformat(),
                expires_at=expiry.isoformat(),
                revoked_at=None,
                granted_by=operator,
                reason=reason,
            )
            self.grants[row["grant_id"]] = row
            await self._event(row, "granted", operator, reason)
            return {"status": "granted", "grant": copy.deepcopy(row)}

    async def revoke(
        self, user_id: str, mode_id: str, operator: str, reason: str
    ) -> ModeGrantResult:
        if not operator or not operator.strip() or not reason or not reason.strip():
            return {"status": "invalid"}
        async with self.lock:
            for row in self.grants.values():
                if (
                    row["user_id"] == user_id
                    and row["mode_id"] == mode_id
                    and row["revoked_at"] is None
                ):
                    row["revoked_at"] = (await _time(utc_now())).isoformat()
                    await self._event(row, "revoked", operator, reason)
                    return {"status": "revoked", "grant": copy.deepcopy(row)}
            return {"status": "not_active"}

    async def get_mode(
        self, sessions: dict[str, dict], user_id: str, session_id: str
    ) -> str | None:
        async with self.lock:
            session = sessions.get(session_id)
            if not session or session["user_id"] != user_id or session.get("ended_at") is not None:
                return None
            return session.get("active_mode_id")

    async def set_mode(
        self,
        sessions: dict[str, dict],
        user_id: str,
        session_id: str,
        mode_id: str | None,
        grant_required: bool,
    ) -> ModeResult:
        if grant_required is None:
            return {"status": "invalid"}
        async with self.lock:
            session = sessions.get(session_id)
            if not session or session["user_id"] != user_id or session.get("ended_at") is not None:
                return {"status": "unavailable"}
            if (
                mode_id not in {None, "daily"}
                and grant_required
                and not await self._active_grant(user_id, mode_id, await _time(utc_now()))
            ):
                return {"status": "unavailable"}
            if mode_id is not None and not await _valid_mode(mode_id):
                raise ValueError("Invalid active Mode identifier")
            session["active_mode_id"] = None if mode_id == "daily" else mode_id
            return {"status": "set"}

    async def create_handoff(
        self,
        sessions: dict[str, dict],
        user_id: str,
        session_id: str,
        source_mode_id: str,
        target_mode_id: str,
        carried_request: str,
        source_grant_required: bool,
        target_grant_required: bool,
    ) -> ModeResult:
        if (
            not await _valid_mode(source_mode_id)
            or not await _valid_mode(target_mode_id)
            or source_mode_id == target_mode_id
            or source_grant_required is None
            or target_grant_required is None
            or not carried_request
            or not carried_request.strip()
        ):
            return {"status": "invalid"}
        async with self.lock:
            session = sessions.get(session_id)
            if (
                not session
                or session["user_id"] != user_id
                or session.get("ended_at") is not None
                or (session.get("active_mode_id") or "daily") != source_mode_id
            ):
                return {"status": "unavailable"}
            now = await _time(utc_now())
            for mode_id, required in (
                (source_mode_id, source_grant_required),
                (target_mode_id, target_grant_required),
            ):
                if (
                    mode_id != "daily"
                    and required
                    and not await self._active_grant(user_id, mode_id, now)
                ):
                    return {"status": "unavailable"}
            row = ModeHandoff(
                handoff_id=str(uuid.uuid4()),
                user_id=user_id,
                session_id=session_id,
                source_mode_id=source_mode_id,
                target_mode_id=target_mode_id,
                source_grant_required=source_grant_required,
                target_grant_required=target_grant_required,
                carried_request=carried_request,
                created_at=now.isoformat(),
                expires_at=(now + MODE_HANDOFF_TTL).isoformat(),
                resolved_at=None,
                resolution=None,
                execution_claimed_at=None, execution_claim_token=None, execution_worker_id=None,
                execution_session_id=None, execution_clock_at=None, execution_attempts=0,
                executed_at=None, execution_plan=[],
                execution_failed_at=None, execution_failure_reason=None,
            )
            self.handoffs[row["handoff_id"]] = row
            return {"status": "pending", "handoff": copy.deepcopy(row)}

    async def resolve_handoff(
        self,
        sessions: dict[str, dict],
        user_id: str,
        session_id: str,
        handoff_id: str,
        confirm: bool,
    ) -> ModeResult:
        if confirm is None:
            return {"status": "invalid"}
        async with self.lock:
            row = self.handoffs.get(handoff_id)
            if (
                not row
                or row["user_id"] != user_id
                or row["session_id"] != session_id
                or row["resolved_at"] is not None
            ):
                return {"status": "unavailable"}
            now = await _time(utc_now())
            session = sessions.get(session_id)
            if await _time(row["expires_at"]) <= now:
                resolution = "expired"
            elif not confirm:
                resolution = "declined"
            elif (
                not session
                or session.get("ended_at") is not None
                or (session.get("active_mode_id") or "daily") != row["source_mode_id"]
            ):
                resolution = "unavailable"
            else:
                resolution = "confirmed"
                for mode_id, required in (
                    (row["source_mode_id"], row["source_grant_required"]),
                    (row["target_mode_id"], row["target_grant_required"]),
                ):
                    if (
                        mode_id != "daily"
                        and required
                        and not await self._active_grant(user_id, mode_id, now)
                    ):
                        resolution = "unavailable"
                        break
            row.update(resolved_at=now.isoformat(), resolution=resolution)
            if resolution == "confirmed":
                session["active_mode_id"] = (
                    None if row["target_mode_id"] == "daily" else row["target_mode_id"]
                )
                return {"status": "confirmed", "handoff": copy.deepcopy(row)}
            return {"status": resolution}


    async def get_conversation(self, user_id: str, mode_id: str, channel: str) -> dict | None:
        async with self.lock:
            row = self.conversations.get((user_id, mode_id, channel))
            return copy.deepcopy(row) if row and row["closed_at"] is None else None

    async def mode_by_conversation(self, user_id: str, channel: str, endpoint: dict) -> str | None:
        key = _json_identity(endpoint)
        async with self.lock:
            row = self.endpoints.get((channel, key))
            return row["mode_id"] if row and row["user_id"] == user_id else None

    async def save_conversation(
        self, users: Iterable[dict], user_id: str, mode_id: str, channel: str,
        endpoint: dict, alias: bool,
    ) -> dict:
        if (not await _valid_mode(mode_id) or not await _valid_mode(channel)
                or type(endpoint) is not dict or not endpoint):
            raise ValueError("Invalid Mode conversation")
        key = _json_identity(endpoint)
        async with self.lock:
            if not any(user["user_id"] == user_id for user in users):
                raise ValueError("Invalid conversation owner")
            previous = self.endpoints.get((channel, key))
            if previous and (previous["user_id"], previous["mode_id"]) != (user_id, mode_id):
                raise ValueError("Conversation endpoint already assigned")
            canonical = self.conversations.get((user_id, mode_id, channel))
            if not alias and canonical and canonical["closed_at"] is None:
                return copy.deepcopy(canonical)
            row = previous or dict(user_id=user_id, mode_id=mode_id, channel=channel,
                                   endpoint=copy.deepcopy(endpoint),
                                   created_at=utc_now().isoformat(),
                                   closed_at=None)
            row["closed_at"] = None
            self.endpoints[channel, key] = row
            canonical_key = (user_id, mode_id, channel)
            if not alias or canonical_key not in self.conversations:
                self.conversations[canonical_key] = row
            return copy.deepcopy(row)

    async def close_conversation(self, user_id: str, mode_id: str, channel: str) -> None:
        async with self.lock:
            for row in self.endpoints.values():
                if (row["user_id"], row["mode_id"], row["channel"]) == (user_id, mode_id, channel):
                    row["closed_at"] = utc_now().isoformat()

    async def list_conversations(self, user_id: str | None) -> list[dict]:
        async with self.lock:
            return copy.deepcopy([row for row in self.conversations.values()
                                  if user_id is None or row["user_id"] == user_id])

    async def claim_execution(
        self, sessions: dict[str, dict], user_id: str, handoff_id: str, worker_id: str,
        execution_session_id: str | None,
    ) -> dict:
        if not worker_id or not worker_id.strip():
            return {"status": "invalid"}
        async with self.lock:
            row = self.handoffs.get(handoff_id)
            if not row or row["user_id"] != user_id or row["resolution"] != "confirmed":
                return {"status": "unavailable"}
            if row.get("executed_at"):
                return {"status": "executed"}
            if row.get("execution_failed_at"):
                return {"status": "failed"}
            now = await _time(utc_now())
            if (row.get("execution_claimed_at") and
                    await _time(row["execution_claimed_at"]) + timedelta(minutes=5) > now):
                return {"status": "busy"}
            bound_id = row.get("execution_session_id") or execution_session_id
            session = sessions.get(bound_id)
            if (not session or session["user_id"] != user_id
                    or (session.get("ended_at") is not None and not row.get("execution_session_id"))
                    or session.get("mode_id", "daily") != row["target_mode_id"]
                    or (row.get("execution_session_id") and execution_session_id is not None
                        and execution_session_id != row["execution_session_id"])):
                row.update(execution_failed_at=now.isoformat(),
                           execution_failure_reason="session_unavailable")
                return {"status": "unavailable", "terminal": True}
            if (row["target_mode_id"] != "daily" and row["target_grant_required"]
                    and not await self._active_grant(user_id, row["target_mode_id"], now)):
                row.update(execution_failed_at=now.isoformat(),
                           execution_failure_reason="target_unavailable")
                return {"status": "unavailable", "terminal": True}
            row.update(execution_session_id=bound_id, execution_claimed_at=now.isoformat(),
                       execution_claim_token=str(uuid.uuid4()), execution_worker_id=worker_id,
                       execution_attempts=row.get("execution_attempts", 0) + 1,
                       execution_clock_at=row.get("execution_clock_at") or now.isoformat(),
                       execution_plan=row.get("execution_plan", []))
            return {"status": "claimed", "handoff": copy.deepcopy(row)}

    async def save_execution_plan(
        self, user_id: str, handoff_id: str, claim_token: str, plan: list[dict],
    ) -> bool:
        if type(plan) is not list or len(plan) > 32:
            return False
        json.dumps(plan, allow_nan=False)
        async with self.lock:
            row = self.handoffs.get(handoff_id)
            if not await self._owns_execution(row, user_id, claim_token):
                return False
            old = row.get("execution_plan", [])
            if _json_identity(plan) == _json_identity(old):
                return True
            if len(plan) != len(old) + 1 or _json_identity(plan[:-1]) != _json_identity(old):
                return False
            row["execution_plan"] = copy.deepcopy(plan)
            return True

    async def _owns_execution(self, row: dict | None, user_id: str, token: str) -> bool:
        return bool(row and row["user_id"] == user_id and row.get("execution_claim_token") == token
                    and row.get("executed_at") is None and row.get("execution_failed_at") is None
                    and row.get("execution_claimed_at")
                    and await _time(row["execution_claimed_at"]) + timedelta(minutes=5)
                    > await _time(utc_now()))

    async def complete_execution(self, user_id: str, handoff_id: str, token: str) -> bool:
        async with self.lock:
            row = self.handoffs.get(handoff_id)
            if not await self._owns_execution(row, user_id, token):
                return False
            row["executed_at"] = (await _time(utc_now())).isoformat()
            return True

    async def fail_execution(self, user_id: str, handoff_id: str, token: str, reason: str) -> bool:
        if reason not in {"execution_failed", "attempts_exhausted", "target_unavailable"}:
            return False
        async with self.lock:
            row = self.handoffs.get(handoff_id)
            if not await self._owns_execution(row, user_id, token):
                return False
            row.update(execution_failed_at=(await _time(utc_now())).isoformat(),
                       execution_failure_reason=reason)
            return True

    async def pending_executions(self, users: Iterable[dict], limit: int) -> list[dict]:
        async with self.lock:
            now = await _time(utc_now())
            profiles = {user["user_id"]: user for user in users}
            result = []
            for row in self.handoffs.values():
                if (row["resolution"] != "confirmed" or row.get("executed_at")
                        or row.get("execution_failed_at")
                        or (row.get("execution_claimed_at") and
                            await _time(row["execution_claimed_at"]) + timedelta(minutes=5) > now)):
                    continue
                result.append({"user_id": row["user_id"], "handoff_id": row["handoff_id"],
                               "execution_session_id": row.get("execution_session_id"),
                               "target_mode_id": row["target_mode_id"],
                               "telegram_chat_id": profiles.get(row["user_id"], {}).get(
                                   "telegram_chat_id")})
            return result[:max(1, min(limit, 100))]
