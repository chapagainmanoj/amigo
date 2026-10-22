"""Owned, versioned Coaching Program transitions; no scheduling, model calls, or logging."""

import asyncio
import copy
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.commands.base import IdempotencyConflictError, InvalidTransitionError, StaleVersionError
from src.utils import utc_now

TERMINAL_STATES = {"completed", "stopped"}


def _utc(value: datetime | str) -> datetime:
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _configuration(goal, success_measure, check_in_days, check_in_time, timezone) -> dict:
    if (
        not isinstance(goal, str)
        or not 1 <= len(goal.strip()) <= 2000
        or not isinstance(success_measure, str)
        or not 1 <= len(success_measure.strip()) <= 2000
        or not isinstance(check_in_days, list)
        or not check_in_days
        or any(type(day) is not int or day not in range(1, 8) for day in check_in_days)
        or len(set(check_in_days)) != len(check_in_days)
    ):
        raise ValueError("Invalid Coaching Program configuration")
    if not isinstance(check_in_time, str) or not re.fullmatch(
        r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", check_in_time
    ):
        raise ValueError("Check-in time must use HH:MM")
    try:
        local_time = time.fromisoformat(check_in_time)
        ZoneInfo(timezone)
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        raise ValueError("Invalid Coaching Program schedule") from None
    if local_time.tzinfo is not None or local_time.second or local_time.microsecond:
        raise ValueError("Check-in time must be local hours and minutes")
    return dict(
        goal=goal,
        success_measure=success_measure,
        check_in_days=sorted(check_in_days),
        check_in_time=local_time.strftime("%H:%M"),
        timezone=timezone,
    )


class LocalCoachingState:
    """Local mirror of the proposed 018 service RPCs; results are detached copies."""

    def __init__(self):
        self.programs: dict[str, dict] = {}
        self.entries: list[dict] = []
        self.approvals: dict[str, dict] = {}
        self.receipts: dict[tuple[str, str], dict] = {}
        self.lock = asyncio.Lock()

    async def _owned(self, user_id: str, program_id: str, version: int | None = None) -> dict:
        row = self.programs.get(program_id)
        if not row or row["user_id"] != user_id:
            raise ValueError("Coaching Program unavailable")
        if version is not None and (type(version) is not int or row["version"] != version):
            raise StaleVersionError("Coaching Program version changed")
        return row

    async def _replay(self, user_id: str, key: str, payload_hash: str) -> dict | None:
        if not key or not key.strip() or not payload_hash:
            raise ValueError("Command replay metadata required")
        old = self.receipts.get((user_id, key))
        if old:
            if old["payload_hash"] != payload_hash:
                raise IdempotencyConflictError("Idempotency key was reused with different input")
            return copy.deepcopy(old["result"])
        return None

    async def _entry(self, row: dict, kind: str, **fields) -> dict:
        entry = dict(
            entry_id=str(uuid.uuid4()),
            user_id=row["user_id"],
            program_id=row["program_id"],
            kind=kind,
            created_at=_utc(utc_now()).isoformat(),
            **fields,
        )
        entry = {
            "action": None,
            "participant_text": None,
            "choice": None,
            "extension_days": None,
            **entry,
        }
        self.entries.append(entry)
        return entry

    async def _result(self, row: dict, key: str, payload_hash: str, entry: dict) -> dict:
        result = copy.deepcopy({"program": row, "entry": entry})
        self.receipts[row["user_id"], key] = dict(payload_hash=payload_hash, result=result)
        return copy.deepcopy(result)

    async def get(self, user_id: str, program_id: str | None = None) -> dict | None:
        async with self.lock:
            if program_id is not None:
                row = self.programs.get(program_id)
                return copy.deepcopy(row) if row and row["user_id"] == user_id else None
            return copy.deepcopy(
                next(
                    (
                        row
                        for row in self.programs.values()
                        if row["user_id"] == user_id and row["state"] not in TERMINAL_STATES
                    ),
                    None,
                )
            )

    async def list_entries(self, user_id: str, program_id: str, limit: int = 20) -> list[dict]:
        async with self.lock:
            await self._owned(user_id, program_id)
            rows = [
                row
                for row in self.entries
                if row["user_id"] == user_id and row["program_id"] == program_id
            ]
            return copy.deepcopy(rows[-max(1, min(limit, 100)) :])

    async def draft(
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
        config = _configuration(goal, success_measure, check_in_days, check_in_time, timezone)
        async with self.lock:
            replay = await self._replay(user_id, idempotency_key, payload_hash)
            if replay:
                return replay
            if any(
                row["user_id"] == user_id and row["state"] not in TERMINAL_STATES
                for row in self.programs.values()
            ):
                raise InvalidTransitionError("A non-terminal Coaching Program already exists")
            now = _utc(utc_now()).isoformat()
            row = dict(
                program_id=str(uuid.uuid4()),
                user_id=user_id,
                **config,
                state="draft",
                starts_at=None,
                ends_at=None,
                extended_count=0,
                version=1,
                created_at=now,
                updated_at=now,
            )
            self.programs[row["program_id"]] = row
            entry = await self._entry(row, "lifecycle", action="draft")
            return await self._result(row, idempotency_key, payload_hash, entry)

    async def issue_approval(self, user_id: str, program_id: str, expected_version: int) -> str:
        async with self.lock:
            row = await self._owned(user_id, program_id, expected_version)
            if row["state"] != "draft":
                raise InvalidTransitionError("Only a draft can be approved")
            token = str(uuid.uuid4())
            self.approvals[_digest(token)] = dict(
                user_id=user_id,
                program_id=program_id,
                version=expected_version,
                summary_digest=_digest(row),
                expires_at=(_utc(utc_now()) + timedelta(minutes=10)).isoformat(),
                used_at=None,
            )
            return token

    async def confirm(
        self, user_id: str, token: str, idempotency_key: str, payload_hash: str
    ) -> dict:
        approval = self.approvals.get(_digest(token))
        if not approval or approval["user_id"] != user_id:
            raise ValueError("Coaching approval unavailable")
        return await self.change(
            user_id,
            approval["program_id"],
            approval["version"],
            "activate",
            idempotency_key,
            payload_hash,
            approval_token=token,
        )

    async def change(
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
        async with self.lock:
            replay = await self._replay(user_id, idempotency_key, payload_hash)
            if replay:
                return replay
            row = await self._owned(user_id, program_id, expected_version)
            if row["state"] in TERMINAL_STATES:
                raise InvalidTransitionError("Coaching Program is terminal")
            now = _utc(utc_now())
            if row["ends_at"] and _utc(row["ends_at"]) <= now:
                raise InvalidTransitionError("Coaching Program term ended")
            event = dict(action=action)
            kind = "lifecycle"
            if action == "activate":
                approval = self.approvals.get(_digest(approval_token)) if approval_token else None
                if (
                    row["state"] != "draft"
                    or not approval
                    or approval["user_id"] != user_id
                    or approval["program_id"] != program_id
                    or approval["version"] != expected_version
                    or approval["summary_digest"] != _digest(row)
                    or approval["used_at"] is not None
                    or _utc(approval["expires_at"]) <= now
                ):
                    raise InvalidTransitionError("Current participant summary approval required")
                approval["used_at"] = now.isoformat()
                row["state"] = "active"
                row["starts_at"] = row["starts_at"] or now.isoformat()
                row["ends_at"] = row["ends_at"] or (now + timedelta(days=14)).isoformat()
            elif action == "pause" and row["state"] == "active":
                row["state"] = "paused"
            elif action == "resume" and row["state"] == "paused":
                row["state"] = "active"
            elif action == "stop":
                row["state"] = "stopped"
            elif action == "extend" and row["state"] in {"active", "paused"}:
                if type(extension_days) is not int or not 1 <= extension_days <= 14:
                    raise ValueError("Explicit extension must be between one and fourteen days")
                row["ends_at"] = (_utc(row["ends_at"]) + timedelta(days=extension_days)).isoformat()
                row["extended_count"] += 1
                event["extension_days"] = extension_days
            elif action == "record_progress" and row["state"] in {"active", "paused"}:
                if (
                    not isinstance(progress_text, str)
                    or not 1 <= len(progress_text.strip()) <= 4000
                ):
                    raise ValueError("Participant-reported progress required")
                kind, event = "progress", {"participant_text": progress_text}
            elif action == "record_weekly_choice" and row["state"] == "active":
                if weekly_choice not in {"continue", "adjust", "pause", "stop"}:
                    raise ValueError("Explicit weekly choice required")
                if weekly_choice in {"adjust", "pause"}:
                    row["state"] = "paused"
                elif weekly_choice == "stop":
                    row["state"] = "stopped"
                kind, event = "weekly_choice", {"choice": weekly_choice}
            else:
                raise InvalidTransitionError("Coaching action is unavailable")
            row["version"] += 1
            row["updated_at"] = now.isoformat()
            entry = await self._entry(row, kind, **event)
            return await self._result(row, idempotency_key, payload_hash, entry)

    async def revise(
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
        config = _configuration(goal, success_measure, check_in_days, check_in_time, timezone)
        async with self.lock:
            replay = await self._replay(user_id, idempotency_key, payload_hash)
            if replay:
                return replay
            row = await self._owned(user_id, program_id, expected_version)
            if row["state"] not in {"draft", "paused"}:
                raise InvalidTransitionError("Pause before revising a Coaching Program")
            if row["ends_at"] and _utc(row["ends_at"]) <= _utc(utc_now()):
                raise InvalidTransitionError("Coaching Program term ended")
            row.update(
                **config,
                state="draft",
                version=row["version"] + 1,
                updated_at=_utc(utc_now()).isoformat(),
            )
            return await self._result(
                row,
                idempotency_key,
                payload_hash,
                await self._entry(row, "lifecycle", action="revise"),
            )

    async def complete_due(self) -> list[dict]:
        async with self.lock:
            result = []
            for row in self.programs.values():
                if (
                    row["state"] not in TERMINAL_STATES
                    and row["ends_at"]
                    and _utc(row["ends_at"]) <= _utc(utc_now())
                ):
                    row.update(
                        state="completed",
                        version=row["version"] + 1,
                        updated_at=_utc(utc_now()).isoformat(),
                    )
                    await self._entry(row, "lifecycle", action="complete")
                    result.append({"program_id": row["program_id"], "user_id": row["user_id"]})
            return result

    async def export(self, user_id: str) -> dict:
        async with self.lock:
            return copy.deepcopy(
                {
                    "programs": [
                        row for row in self.programs.values() if row["user_id"] == user_id
                    ],
                    "entries": [row for row in self.entries if row["user_id"] == user_id],
                }
            )

    async def delete(self, user_id: str) -> None:
        async with self.lock:
            self.programs = {
                key: row for key, row in self.programs.items() if row["user_id"] != user_id
            }
            self.entries = [row for row in self.entries if row["user_id"] != user_id]
            self.approvals = {
                key: row for key, row in self.approvals.items() if row["user_id"] != user_id
            }
            self.receipts = {key: row for key, row in self.receipts.items() if key[0] != user_id}

    async def list_active(self) -> list[dict]:
        async with self.lock:
            now = _utc(utc_now())
            return copy.deepcopy(
                [
                    row
                    for row in self.programs.values()
                    if row["state"] == "active" and row["ends_at"] and _utc(row["ends_at"]) > now
                ]
            )
