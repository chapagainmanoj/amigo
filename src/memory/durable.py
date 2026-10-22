"""Explicit-first owned Memory state. Admission stays off until independently reviewed.

Candidates are application-local. This module stores only confirmation digests until the
participant confirms, and idempotency receipts contain references rather than text copies.
"""

import asyncio
import copy
import hashlib
import json
import re
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.commands.base import IdempotencyConflictError, InvalidTransitionError, StaleVersionError
from src.utils import utc_now

MEMORY_POLICY_VERSION = "memory-explicit-v1"
CATEGORIES = {"preference", "routine", "constraint", "goal", "project", "context"}
STATES = {"active", "needs_confirmation", "inactive", "superseded", "expired", "forgotten"}
PURPOSES = {
    "personalize": "Personalize wording using a confirmed fact",
    "suggestion": "Support a relevant suggestion",
    "preference": "Use a confirmed preference for the current request",
}
PAYLOAD_FIELDS = (
    "category",
    "text",
    "source_mode_id",
    "source_channel",
    "source_message_id",
    "source_date",
    "creation_path",
    "scopes",
    "valid_until",
)


def _now(value=None):
    value = utc_now() if value is None else value
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def normalize_memory_payload(payload):
    if not isinstance(payload, dict) or set(payload) - set(PAYLOAD_FIELDS):
        raise ValueError("Invalid Memory payload")
    value = {field: copy.deepcopy(payload.get(field)) for field in PAYLOAD_FIELDS}
    if (
        value["category"] not in CATEGORIES
        or not isinstance(value["text"], str)
        or not 1 <= len(value["text"].strip()) <= 2000
        or value["creation_path"]
        not in {"participant_requested", "amigo_proposed", "dashboard_explicit"}
        or any(
            not isinstance(value[field], str)
            or re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value[field]) is None
            for field in ("source_mode_id", "source_channel")
        )
        or not isinstance(value["scopes"], list)
        or not 1 <= len(value["scopes"]) <= 4
        or any(
            not isinstance(scope, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,31}", scope) is None
            for scope in value["scopes"]
        )
    ):
        raise ValueError("Invalid Memory payload")
    value["scopes"] = sorted(set(value["scopes"]))
    for field in ("source_date", "valid_until"):
        if value[field] is not None:
            if (
                not isinstance(value[field], str)
                or date.fromisoformat(value[field]).isoformat() != value[field]
            ):
                raise ValueError("Invalid Memory date")
        elif field == "source_date":
            raise ValueError("Memory provenance date required")
    if value["source_message_id"] is not None:
        value["source_message_id"] = str(uuid.UUID(value["source_message_id"]))
    return value


def memory_payload_digest(payload):
    """Normative encoding: ordered JSON array, UTF-8, spaces after commas, raw Unicode."""
    value = normalize_memory_payload(payload)
    encoded = json.dumps([value[field] for field in PAYLOAD_FIELDS], ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def memory_inventory_digest(rows):
    pairs = sorted(
        [row["memory_id"], row["version"]] for row in rows if row["state"] != "forgotten"
    )
    return hashlib.sha256(json.dumps(pairs, ensure_ascii=False).encode()).hexdigest()


class LocalMemoryState:
    """One local mutex also serializes the five-owner admission cap across all participants."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.admission_enabled = False
        self.settings = {}
        self.memories = {}
        self.uses = []
        self.claims = {}
        self.receipts = {}

    async def _settings(self, user_id):
        return self.settings.get(
            user_id,
            dict(
                user_id=user_id,
                enabled=False,
                learning_paused=False,
                use_paused=False,
                policy_version=None,
                opted_in_at=None,
                version=0,
            ),
        )

    async def get_settings(self, user_id):
        async with self.lock:
            return copy.deepcopy(await self._settings(user_id))

    async def _owned(self, user_id, memory_id, version=None):
        rows = [
            row
            for (item_id, _), row in self.memories.items()
            if item_id == memory_id and row["user_id"] == user_id
        ]
        if not rows:
            raise ValueError("Memory unavailable")
        row = max(rows, key=lambda item: item["version"])
        if version is not None and row["version"] != version:
            raise StaleVersionError("Memory version changed")
        return row

    async def _replay(self, user_id, key, digest, operation):
        if not key or not digest:
            raise ValueError("Memory replay metadata required")
        old = self.receipts.get((user_id, key))
        if old:
            if old["payload_hash"] != digest or old["operation"] != operation:
                raise IdempotencyConflictError("Memory command key was reused")
            result = copy.deepcopy(old["result"])
            if "memory_id" in result and result.get("version"):
                result = {
                    "memory": copy.deepcopy(self.memories[result["memory_id"], result["version"]]),
                    "settings": copy.deepcopy(await self._settings(user_id)),
                }
            return result
        return None

    async def _receipt(self, user_id, key, digest, result, operation):
        retained = (
            {"memory_id": result["memory"]["memory_id"], "version": result["memory"]["version"]}
            if "memory" in result
            else copy.deepcopy(result)
        )
        self.receipts[user_id, key] = dict(
            payload_hash=digest, result=retained, operation=operation
        )
        return copy.deepcopy(result)

    async def prepare(
        self,
        user_id,
        operation,
        preview_digest,
        expected_settings_version,
        memory_id=None,
        expected_memory_version=None,
    ):
        async with self.lock:
            if (
                operation not in {"save", "correct", "reconfirm", "share", "forget_all"}
                or re.fullmatch(r"[0-9a-f]{64}", preview_digest or "") is None
            ):
                raise ValueError("Invalid Memory confirmation")
            settings = await self._settings(user_id)
            if settings["version"] != expected_settings_version:
                raise StaleVersionError("Memory settings changed")
            if operation != "forget_all" and (
                not self.admission_enabled or settings["learning_paused"]
            ):
                raise InvalidTransitionError(
                    "Memory admission is unavailable or learning is paused"
                )
            if operation in {"correct", "reconfirm", "share"}:
                await self._owned(user_id, memory_id, expected_memory_version)
            token = secrets.token_hex(32)
            self.claims[hashlib.sha256(token.encode()).hexdigest()] = dict(
                user_id=user_id,
                operation=operation,
                preview_digest=preview_digest,
                settings_version=expected_settings_version,
                memory_id=memory_id,
                memory_version=expected_memory_version,
                expires_at=(_now() + timedelta(minutes=10)).isoformat(),
                consumed_at=None,
            )
            return dict(token=token, expires_at=(_now() + timedelta(minutes=10)).isoformat())

    async def _claim(self, user_id, token):
        claim = self.claims.get(hashlib.sha256(token.encode()).hexdigest())
        if (
            not claim
            or claim["user_id"] != user_id
            or claim["consumed_at"] is not None
            or _now(claim["expires_at"]) <= _now()
        ):
            raise InvalidTransitionError("Memory confirmation unavailable")
        settings = await self._settings(user_id)
        if settings["version"] != claim["settings_version"]:
            raise StaleVersionError("Memory settings changed")
        return claim, copy.deepcopy(settings)

    async def confirm(
        self,
        user,
        messages,
        sessions,
        token,
        payload,
        key,
        digest,
        enable_memory=False,
        policy_version=None,
    ):
        async with self.lock:
            user_id = user["user_id"]
            replay = await self._replay(user_id, key, digest, "confirm_memory_save")
            if replay is not None:
                return replay
            claim, settings = await self._claim(user_id, token)
            if (
                not self.admission_enabled
                or settings["learning_paused"]
                or claim["operation"] == "forget_all"
            ):
                raise InvalidTransitionError(
                    "Memory admission is unavailable or learning is paused"
                )
            value = normalize_memory_payload(payload)
            if memory_payload_digest(value) != claim["preview_digest"]:
                raise InvalidTransitionError("Memory preview changed")
            message_id = value["source_message_id"]
            if message_id is not None:
                message = next(
                    (
                        row
                        for row in messages
                        if row["message_id"] == message_id and row["user_id"] == user_id
                    ),
                    None,
                )
                session = sessions.get(message["session_id"]) if message else None
                if (
                    not session
                    or session["user_id"] != user_id
                    or session.get("mode_id", "daily") != value["source_mode_id"]
                ):
                    raise ValueError("Memory source unavailable")
            day = _now().astimezone(ZoneInfo(user.get("timezone") or "UTC")).date()
            if value["valid_until"] and date.fromisoformat(value["valid_until"]) < day:
                raise InvalidTransitionError("Memory validity date has passed")
            if not settings["enabled"]:
                if not enable_memory or policy_version != MEMORY_POLICY_VERSION:
                    raise InvalidTransitionError("Memory opt-in and exact first item required")
                if sum(row["enabled"] for row in self.settings.values()) >= 5:
                    raise InvalidTransitionError("Memory trial admission cap reached")
                settings.update(
                    enabled=True, policy_version=policy_version, opted_in_at=_now().isoformat()
                )
            old = None
            if claim["operation"] != "save":
                old = await self._owned(user_id, claim["memory_id"], claim["memory_version"])
                if old["state"] in {"forgotten", "superseded"}:
                    raise InvalidTransitionError("Memory version is unavailable")
                if claim["operation"] in {"reconfirm", "share"} and any(
                    old[field] != value[field] for field in ("text", "category")
                ):
                    raise InvalidTransitionError("Memory confirmation changed meaning")
                if claim["operation"] != "share" and old["scopes"] != value["scopes"]:
                    raise InvalidTransitionError("Sharing requires a separate exact preview")
                if claim["operation"] == "share" and old["valid_until"] != value["valid_until"]:
                    raise InvalidTransitionError("Sharing cannot change temporal validity")
            elif value["source_mode_id"] not in value["scopes"]:
                raise ValueError("The originating Mode requires an explicit initial scope")
            now = _now()
            item_id = old["memory_id"] if old else str(uuid.uuid4())
            version = old["version"] + 1 if old else 1
            goal_state = old.get("goal_state", "ongoing") if old else "ongoing"
            row = dict(
                user_id=user_id,
                memory_id=item_id,
                version=version,
                **value,
                state="active" if goal_state == "ongoing" else "inactive",
                goal_state=goal_state,
                created_at=now.isoformat(),
                confirmed_at=now.isoformat(),
                reconfirm_at=None
                if value["valid_until"]
                else (
                    now + timedelta(days=180 if value["category"] == "preference" else 90)
                ).isoformat(),
                supersedes_version=old["version"] if old else None,
            )
            if old:
                old["state"] = "superseded"
            self.memories[item_id, version] = row
            claim["consumed_at"] = now.isoformat()
            settings["version"] += 1
            self.settings[user_id] = settings
            return await self._receipt(
                user_id,
                key,
                digest,
                {"memory": row, "settings": settings},
                operation="confirm_memory_save",
            )

    async def _effective(self, row, user):
        if row["state"] != "active":
            return row["state"]
        day = _now().astimezone(ZoneInfo(user.get("timezone") or "UTC")).date()
        if row["valid_until"] and date.fromisoformat(row["valid_until"]) < day:
            return "expired"
        if row["reconfirm_at"] and _now(row["reconfirm_at"]) <= _now():
            return "needs_confirmation"
        return "inactive" if row.get("goal_state") != "ongoing" else "active"

    async def transition(self, user, memory_id, version, action, key, digest):
        async with self.lock:
            user_id = user["user_id"]
            replay = await self._replay(user_id, key, digest, "transition_memory")
            if replay is not None:
                return replay
            row = await self._owned(user_id, memory_id, version)
            if row["state"] in {"forgotten", "superseded"}:
                raise InvalidTransitionError("Memory version is unavailable")
            old = row
            row = copy.deepcopy(old)
            if action == "inactive":
                row["state"] = "inactive"
            elif action == "use_again":
                probe = {**row, "state": "active"}
                if await self._effective(probe, user) != "active":
                    raise InvalidTransitionError("Memory needs confirmation or remains completed")
                row["state"] = "active"
            elif action in {"complete_goal", "cancel_goal"} and row["category"] in {
                "goal",
                "project",
            }:
                row.update(
                    state="inactive",
                    goal_state="completed" if action == "complete_goal" else "cancelled",
                )
            else:
                raise InvalidTransitionError("Invalid Memory action")
            row["version"] += 1
            row["supersedes_version"] = old["version"]
            old["state"] = "superseded"
            self.memories[memory_id, row["version"]] = row
            settings = copy.deepcopy(await self._settings(user_id))
            settings["version"] += 1
            self.settings[user_id] = settings
            return await self._receipt(
                user_id,
                key,
                digest,
                {"memory": row, "settings": settings},
                operation="transition_memory",
            )

    async def pauses(self, user_id, version, learning, use, key, digest):
        async with self.lock:
            replay = await self._replay(user_id, key, digest, "set_memory_pauses")
            if replay is not None:
                return replay
            settings = copy.deepcopy(await self._settings(user_id))
            if settings["version"] != version:
                raise StaleVersionError("Memory settings changed")
            if (learning is None and use is None) or any(
                type(value) is not bool for value in (learning, use) if value is not None
            ):
                raise ValueError("Explicit Memory pause controls required")
            if learning is not None:
                settings["learning_paused"] = learning
            if use is not None:
                settings["use_paused"] = use
            settings["version"] += 1
            self.settings[user_id] = settings
            if learning is True:
                for claim in self.claims.values():
                    if claim["user_id"] == user_id and claim["operation"] != "forget_all":
                        claim["consumed_at"] = _now().isoformat()
            return await self._receipt(
                user_id, key, digest, settings, operation="set_memory_pauses"
            )

    async def read(self, user, mode_id, turn_id, purpose, query):
        if (
            purpose not in PURPOSES
            or not turn_id
            or not isinstance(query, str)
            or len(query) > 1000
        ):
            raise ValueError("Invalid Memory use")
        async with self.lock:
            user_id = user["user_id"]
            settings = await self._settings(user_id)
            if (
                not self.admission_enabled
                or not settings["enabled"]
                or settings["use_paused"]
                or mode_id == "reflect"
            ):
                return []
            terms = set(re.findall(r"[a-z0-9]+", query.lower()))
            if not terms:
                return []
            already = [
                use for use in self.uses if use["user_id"] == user_id and use["turn_id"] == turn_id
            ]
            chosen = {(use["memory_id"], use["version"]) for use in already}
            eligible = []
            for identity, row in self.memories.items():
                if (
                    row["user_id"] != user_id
                    or mode_id not in row["scopes"]
                    or await self._effective(row, user) != "active"
                ):
                    continue
                overlap = len(terms & set(re.findall(r"[a-z0-9]+", row["text"].lower())))
                if overlap and (not chosen or identity in chosen):
                    eligible.append((overlap, row))
            eligible.sort(key=lambda pair: (-pair[0], pair[1]["memory_id"], pair[1]["version"]))
            rows = [row for _, row in eligible[:3]]
            for row in rows:
                if (row["memory_id"], row["version"]) not in chosen:
                    self.uses.append(
                        dict(
                            user_id=user_id,
                            memory_id=row["memory_id"],
                            version=row["version"],
                            turn_id=turn_id,
                            purpose=purpose,
                            used_at=_now().isoformat(),
                        )
                    )
            return [
                {**copy.deepcopy(row), "untrusted": True, "use_purpose": PURPOSES[purpose]}
                for row in rows
            ]

    async def inspect(self, user, states=None, limit=100, offset=0):
        async with self.lock:
            rows = []
            for row in self.memories.values():
                if row["user_id"] == user["user_id"]:
                    item = copy.deepcopy(row)
                    item["state"] = await self._effective(row, user)
                    if states is None or item["state"] in states:
                        rows.append(item)
            rows.sort(key=lambda row: (row["memory_id"], row["version"]))
            return dict(
                memories=rows[max(0, offset) : max(0, offset) + max(1, min(limit, 1000))],
                uses=[copy.deepcopy(row) for row in self.uses if row["user_id"] == user["user_id"]],
                settings=copy.deepcopy(await self._settings(user["user_id"])),
            )

    async def export(self, user):
        async with self.lock:
            rows = [
                {**copy.deepcopy(row), "state": await self._effective(row, user)}
                for row in self.memories.values()
                if row["user_id"] == user["user_id"]
            ]
            rows.sort(key=lambda row: (row["memory_id"], row["version"]))
            return dict(
                memories=rows,
                uses=[copy.deepcopy(row) for row in self.uses if row["user_id"] == user["user_id"]],
                settings=copy.deepcopy(await self._settings(user["user_id"])),
            )

    async def _purge(self, user_id, memory_ids):
        for row in self.memories.values():
            if row["user_id"] == user_id and row["memory_id"] in memory_ids:
                row.update(
                    text=None,
                    source_message_id=None,
                    source_mode_id=None,
                    source_channel=None,
                    source_date=None,
                    creation_path=None,
                    scopes=[],
                    valid_until=None,
                    reconfirm_at=None,
                    state="forgotten",
                )
        self.uses[:] = [
            row
            for row in self.uses
            if not (row["user_id"] == user_id and row["memory_id"] in memory_ids)
        ]
        for claim in self.claims.values():
            if claim["user_id"] == user_id and (
                claim["memory_id"] in memory_ids or claim["operation"] == "forget_all"
            ):
                claim["consumed_at"] = _now().isoformat()

    async def forget(self, user_id, memory_id, version, key, digest):
        async with self.lock:
            replay = await self._replay(user_id, key, digest, "forget_memory")
            if replay is not None:
                return replay
            await self._owned(user_id, memory_id, version)
            await self._purge(user_id, {memory_id})
            settings = copy.deepcopy(await self._settings(user_id))
            settings["version"] += 1
            self.settings[user_id] = settings
            return await self._receipt(
                user_id,
                key,
                digest,
                dict(status="forgotten", memory_id=memory_id),
                operation="forget_memory",
            )

    async def forget_all(self, user_id, token, key, digest):
        async with self.lock:
            replay = await self._replay(user_id, key, digest, "confirm_forget_all_memory")
            if replay is not None:
                return replay
            claim, settings = await self._claim(user_id, token)
            rows = [row for row in self.memories.values() if row["user_id"] == user_id]
            if (
                claim["operation"] != "forget_all"
                or memory_inventory_digest(rows) != claim["preview_digest"]
            ):
                raise InvalidTransitionError("Memory inventory changed")
            identities = {row["memory_id"] for row in rows if row["state"] != "forgotten"}
            await self._purge(user_id, identities)
            # Forget All also invalidates every outstanding ephemeral candidate's metadata.
            for item in self.claims.values():
                if item["user_id"] == user_id:
                    item["consumed_at"] = _now().isoformat()
            settings["version"] += 1
            self.settings[user_id] = settings
            return await self._receipt(
                user_id,
                key,
                digest,
                dict(status="forgotten", count=len(identities)),
                operation="confirm_forget_all_memory",
            )
