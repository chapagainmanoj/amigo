"""Mode Store DTOs and atomic local mirrors of migration 016's RPC semantics.

Registry/live checks and participant confirmation belong to trusted application adapters.
This module never authorizes model arguments, executes a carried request, or queries Supabase.
"""

import asyncio
import copy
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
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


class ModeResult(TypedDict):
    status: Literal["invalid", "unavailable", "set", "pending", "confirmed", "declined", "expired"]
    handoff: NotRequired[ModeHandoff]


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
