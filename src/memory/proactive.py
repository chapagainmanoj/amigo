"""Content-free local mirror of shared proactive reservations and coaching outbox claims."""

import asyncio
import copy
import re
import uuid
from datetime import UTC, datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from src.utils import utc_now


def instant(value):
    value = datetime.fromisoformat(value) if isinstance(value, str) else value
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def local_day(value, timezone):
    return instant(value).astimezone(ZoneInfo(timezone)).date().isoformat()


class LocalProactiveState:
    """Trusted Store adapters supply canonical profile/program/grant containers.

    No participant may supply a budget limit or legacy flag. Legacy reservations are an
    explicit cutover debt, not a claim that existing over-budget commitments complied.
    """

    def __init__(self):
        self.lock = asyncio.Lock()
        self.reservations: dict[tuple[str, str], dict] = {}
        self.deliveries: dict[tuple[str, str], dict] = {}
        self.consents: dict[tuple[str, str], dict] = {}
        self.replies: dict[tuple[str, str], str] = {}

    async def set_consent(self, user_id, scope, policy_version, country_code=None, withdraw=False):
        if (
            scope not in {"coaching-v1", "reflect-v1"}
            or (
                not withdraw and (not isinstance(policy_version, str) or not policy_version.strip())
            )
            or type(withdraw) is not bool
            or (country_code is not None and re.fullmatch(r"[A-Za-z]{2}", country_code) is None)
        ):
            raise ValueError("Consent requires an approved scope and policy version")
        async with self.lock:
            old = self.consents.get((user_id, scope), {})
            row = dict(
                user_id=user_id,
                scope=scope,
                policy_version=policy_version or old.get("policy_version"),
                country_code=country_code.upper() if country_code else old.get("country_code"),
                acknowledged_at=instant(utc_now()).isoformat(),
                withdrawn_at=instant(utc_now()).isoformat() if withdraw else None,
            )
            self.consents[user_id, scope] = row
            if withdraw and scope == "coaching-v1":
                for delivery in self.deliveries.values():
                    if delivery["user_id"] == user_id and delivery["state"] in {
                        "pending",
                        "claimed",
                    }:
                        delivery.update(
                            state="cancelled", finished_at=instant(utc_now()).isoformat(),
                            cancellation_reason="consent_withdrawn",
                        )
                        self.reservations[user_id, delivery["delivery_key"]]["state"] = "cancelled"
            return copy.deepcopy(row)

    async def get_consent(self, user_id, scope):
        async with self.lock:
            return copy.deepcopy(self.consents.get((user_id, scope)))

    async def consent(self, user_id, policy_version=None):
        return await self.set_consent(
            user_id, "coaching-v1", policy_version, withdraw=policy_version is None
        )

    async def has_consent(self, user_id):
        async with self.lock:
            return await self._consented(user_id)

    async def _consented(self, user_id):
        row = self.consents.get((user_id, "coaching-v1"))
        return bool(
            row and row.get("policy_version") == "coaching-v1" and row.get("withdrawn_at") is None
        )

    async def _reserve(self, user, key, kind, scheduled_at, program_id=None, *, legacy=False):
        if not user or not key or kind not in {"recovery", "coaching"}:
            raise ValueError("Invalid proactive reservation")
        user_id = user["user_id"]
        await self._discard_reminder_reservations()
        at = instant(scheduled_at)
        timezone = user.get("timezone") or "UTC"
        day = local_day(at, timezone)
        old = self.reservations.get((user_id, key))
        if old and old["state"] != "cancelled":
            if (
                old["kind"] != kind
                or instant(old["scheduled_at"]) != at
                or old.get("program_id") != program_id
            ):
                raise ValueError("Proactive key was reused with different input")
            return {"status": "already_reserved", "reservation": copy.deepcopy(old)}
        occupied = sum(
            row["user_id"] == user_id
            and row["state"] != "cancelled"
            and (row["local_day"] == day or local_day(row["scheduled_at"], timezone) == day)
            for row in self.reservations.values()
        )
        limit = user.get("daily_message_budget")
        limit = 4 if limit is None else max(0, int(limit))
        coaching_occupied = kind == "coaching" and any(
            row["user_id"] == user_id
            and row["kind"] == "coaching"
            and row["state"] != "cancelled"
            and (row["local_day"] == day or local_day(row["scheduled_at"], timezone) == day)
            for row in self.reservations.values()
        )
        if not legacy and (occupied >= limit or coaching_occupied):
            return {"status": "budget_exhausted"}
        row = dict(
            user_id=user_id,
            delivery_key=key,
            kind=kind,
            program_id=program_id,
            scheduled_at=at.isoformat(),
            timezone=timezone,
            local_day=day,
            state="reserved",
            legacy_debt=legacy and occupied >= limit,
        )
        self.reservations[user_id, key] = row
        return {"status": "reserved", "reservation": copy.deepcopy(row)}

    async def reserve(self, user, key, kind, scheduled_at, program_id=None):
        async with self.lock:
            return await self._reserve(user, key, kind, scheduled_at, program_id)

    async def _discard_reminder_reservations(self):
        for key, row in list(self.reservations.items()):
            if row["kind"] == "reminder":
                del self.reservations[key]

    async def backfill_reminders(self, users, reminders, occurrences=None, attempts=None):
        """Old Reminder reservations are no longer proactive capacity; commitments stay intact."""
        async with self.lock:
            await self._discard_reminder_reservations()

    async def mark_dispatch(self, user, key):
        if not user:
            return False
        async with self.lock:
            await self._discard_reminder_reservations()
            user_id = user["user_id"]
            row = self.reservations.get((user_id, key))
            if not row or row["kind"] != "recovery" or row["state"] != "reserved":
                return False
            zone = user.get("timezone") or "UTC"
            day = local_day(utc_now(), zone)
            occupied = sum(
                item["user_id"] == user_id and item["state"] != "cancelled"
                and (item["local_day"] == day or local_day(item["scheduled_at"], zone) == day)
                for item in self.reservations.values()
            )
            limit = user.get("daily_message_budget")
            limit = 4 if limit is None else max(0, int(limit))
            if occupied > limit or local_day(row["scheduled_at"], zone) != day:
                row["state"] = "cancelled"
                return False
            row["state"] = "dispatched"
            return True

    async def finish_delivery(self, user_id, key, outcome):
        if outcome not in {"accepted", "rejected", "uncertain"}:
            raise ValueError("Invalid proactive outcome")
        async with self.lock:
            row = self.reservations.get((user_id, key))
            if not row or row["kind"] != "recovery" or row["state"] != "dispatched":
                return False
            row["state"] = outcome
            return True

    async def release(self, user_id, key):
        async with self.lock:
            row = self.reservations.get((user_id, key))
            if row is None or row["state"] != "reserved":
                return False
            row["state"] = "cancelled"
            return True

    async def _eligible(self, user_id, program, grants, now):
        return bool(
            program
            and program["user_id"] == user_id
            and program["state"] == "active"
            and instant(program["starts_at"]) <= now < instant(program["ends_at"])
            and await self._consented(user_id)
            and any(
                row["user_id"] == user_id
                and row["mode_id"] == "coach"
                and row.get("revoked_at") is None
                and instant(row["expires_at"]) > now
                for row in grants
            )
        )

    async def enqueue(
        self,
        user,
        programs,
        grants,
        program_id,
        expected_version,
        day,
        kind,
        scheduled_at,
        key,
        *,
        activated=False,
    ):
        async with self.lock:
            program = programs.get(program_id)
            now = instant(utc_now())
            if (
                not activated
                or kind not in {"check_in", "follow_up", "weekly_review"}
                or not await self._eligible(user["user_id"], program, grants, now)
                or program["version"] != expected_version
            ):
                return {"status": "unavailable"}
            if day != local_day(scheduled_at, program["timezone"]):
                return {"status": "invalid"}
            existing = next(
                (
                    row
                    for row in self.deliveries.values()
                    if row["program_id"] == program_id and row["local_day"] == day
                ),
                None,
            )
            if existing:
                return {"status": "already_queued", "delivery": copy.deepcopy(existing)}
            reserved = await self._reserve(user, key, "coaching", scheduled_at, program_id)
            if reserved["status"] == "budget_exhausted":
                return reserved
            row = dict(
                user_id=user["user_id"],
                program_id=program_id,
                program_version=expected_version,
                delivery_key=key,
                local_day=day,
                kind=kind,
                scheduled_at=instant(scheduled_at).isoformat(),
                state="pending",
                claim_token=None,
                claimed_at=None,
                worker_id=None,
                dispatched_at=None,
                finished_at=None,
                cancellation_reason=None,
            )
            self.deliveries[user["user_id"], key] = row
            return {"status": "queued", "delivery": copy.deepcopy(row)}

    async def claim(self, worker_id, limit=25):
        async with self.lock:
            now = instant(utc_now())
            selected = []
            for row in sorted(self.deliveries.values(), key=lambda row: row["scheduled_at"]):
                if row["state"] == "dispatched" and instant(
                    row["dispatched_at"]
                ) <= now - timedelta(minutes=5):
                    row.update(state="uncertain", finished_at=now.isoformat())
                    self.reservations[row["user_id"], row["delivery_key"]]["state"] = "uncertain"
                reclaim = row["state"] == "claimed" and instant(
                    row["claimed_at"]
                ) <= now - timedelta(minutes=5)
                if (row["state"] == "pending" or reclaim) and instant(row["scheduled_at"]) <= now:
                    row.update(
                        state="claimed",
                        claim_token=str(uuid.uuid4()),
                        claimed_at=now.isoformat(),
                        worker_id=worker_id,
                    )
                    selected.append(copy.deepcopy(row))
                    if len(selected) >= max(1, min(limit, 100)):
                        break
            return selected

    async def _cancellation_reason(self, user_id, program, row, entries, now):
        if not program or program["user_id"] != user_id:
            return "program_unavailable"
        if program["state"] in {"paused", "stopped", "completed"}:
            return "program_" + program["state"]
        today = local_day(now, program["timezone"])
        if any(
            entry["user_id"] == user_id
            and entry["program_id"] == program["program_id"]
            and entry["kind"] == "progress"
            and local_day(entry["created_at"], program["timezone"]) == today
            for entry in entries
        ):
            return "progress_logged_today"
        if program["version"] != row["program_version"]:
            return "program_changed"
        return "ineligible"

    async def dispatch(
        self, user_id, key, token, programs, grants, user=None, activated=False, entries=()
    ):
        async with self.lock:
            await self._discard_reminder_reservations()
            row = self.deliveries.get((user_id, key))
            now = instant(utc_now())
            if (
                not row
                or row["state"] != "claimed"
                or row["claim_token"] != token
                or instant(row["claimed_at"]) <= now - timedelta(minutes=5)
            ):
                return False
            program = programs.get(row["program_id"])
            reason = await self._cancellation_reason(user_id, program, row, entries, now)
            invalid = (
                reason == "progress_logged_today"
                or not activated
                or not await self._eligible(user_id, program, grants, now)
            )
            if not invalid:
                local = now.astimezone(ZoneInfo(program["timezone"]))
                profile = user or {}
                wake = profile.get("wake_time") or "07:30"
                sleep = profile.get("sleep_time") or "23:00"
                profile_local = now.astimezone(ZoneInfo(profile.get("timezone") or "UTC"))
                wall = profile_local.strftime("%H:%M")
                awake = wake <= wall < sleep if wake < sleep else wall >= wake or wall < sleep
                reply = self.replies.get((user_id, program["program_id"]))
                unanswered = sum(
                    item["program_id"] == program["program_id"]
                    and item["state"] in {"accepted", "uncertain", "dispatched"}
                    and (
                        reply is None
                        or instant(item.get("dispatched_at") or item["scheduled_at"])
                        > instant(reply)
                    )
                    for item in self.deliveries.values()
                )
                profile_day = profile_local.date().isoformat()
                occupied = [
                    item
                    for item in self.reservations.values()
                    if item["user_id"] == user_id
                    and item["state"] != "cancelled"
                    and (
                        item["local_day"] == profile_day
                        or local_day(item["scheduled_at"], profile.get("timezone") or "UTC")
                        == profile_day
                    )
                ]
                limit = profile.get("daily_message_budget")
                limit = 4 if limit is None else max(0, int(limit))
                invalid = (
                    len(occupied) > limit
                    or any(
                        item["kind"] == "coaching" and item["delivery_key"] != key
                        for item in occupied
                    )
                    or program["version"] != row["program_version"]
                    or local.date().isoformat() != row["local_day"]
                    or local.isoweekday() not in program["check_in_days"]
                    or not awake
                    or not instant(row["scheduled_at"])
                    <= now
                    <= instant(row["scheduled_at"]) + timedelta(minutes=15)
                    or unanswered >= 2
                    or (unanswered == 1 and row["kind"] != "follow_up")
                    or (unanswered == 0 and row["kind"] == "follow_up")
                )
            if invalid:
                row.update(
                    state="cancelled", finished_at=now.isoformat(), cancellation_reason=reason
                )
                self.reservations[user_id, key]["state"] = "cancelled"
                return False
            row.update(state="dispatched", dispatched_at=now.isoformat())
            self.reservations[user_id, key]["state"] = "dispatched"
            return True

    async def finish(self, user_id, key, token, outcome, programs=None, entries=()):
        if outcome not in {"accepted", "rejected", "uncertain", "cancelled"}:
            raise ValueError("Invalid coaching delivery outcome")
        async with self.lock:
            row = self.deliveries.get((user_id, key))
            if (
                not row
                or row["claim_token"] != token
                or row["state"] not in {"claimed", "dispatched"}
            ):
                return False
            if row["state"] == "dispatched" and outcome == "cancelled":
                outcome = "uncertain"
            reason = (
                await self._cancellation_reason(
                    user_id,
                    (programs or {}).get(row["program_id"]),
                    row,
                    entries,
                    instant(utc_now()),
                )
                if outcome == "cancelled"
                else None
            )
            row.update(
                state=outcome,
                finished_at=instant(utc_now()).isoformat(),
                cancellation_reason=reason,
            )
            self.reservations[user_id, key]["state"] = outcome
            return True

    async def cancel_inactive(self, programs):
        async with self.lock:
            for row in self.deliveries.values():
                program = programs.get(row["program_id"])
                if (not program or program["state"] != "active") and row["state"] in {
                    "pending",
                    "claimed",
                }:
                    row.update(
                        state="cancelled",
                        finished_at=instant(utc_now()).isoformat(),
                        cancellation_reason=(
                            "program_unavailable" if not program else
                            "program_" + program["state"]
                            if program["state"] in {"paused", "stopped", "completed"}
                            else "ineligible"
                        ),
                    )
                    self.reservations[row["user_id"], row["delivery_key"]]["state"] = "cancelled"

    async def purge_programs(self, user_id, program_ids):
        async with self.lock:
            for key, row in list(self.deliveries.items()):
                if row["user_id"] == user_id and row["program_id"] in program_ids:
                    del self.deliveries[key]
                    reservation = self.reservations.get(key)
                    if reservation and reservation["state"] in {
                        "dispatched",
                        "accepted",
                        "rejected",
                        "uncertain",
                    }:
                        reservation["program_id"] = None
                    else:
                        self.reservations.pop(key, None)
            for key in list(self.replies):
                if key[0] == user_id and key[1] in program_ids:
                    del self.replies[key]
            for row in self.reservations.values():
                if row["user_id"] == user_id and row.get("program_id") in program_ids:
                    if row["state"] == "reserved":
                        row["state"] = "cancelled"
                    row["program_id"] = None

    async def note_reply(self, user_id, program_id):
        async with self.lock:
            self.replies[user_id, program_id] = instant(utc_now()).isoformat()

    async def history(self, user_id, program_id):
        async with self.lock:
            return {
                "last_reply_at": self.replies.get((user_id, program_id)),
                "deliveries": [
                    copy.deepcopy(row)
                    for row in self.deliveries.values()
                    if row["user_id"] == user_id and row["program_id"] == program_id
                ],
            }


# These helpers mirror INSERT/UPDATE Reminder budget triggers for the local Stores.
# No new Reminder path may bypass the transaction wrapper; SDK-backed MemoryStore uses SQL.
def _restore_container(target, snapshot):
    """Roll back in place so callers holding local fixture row references see the rollback too."""
    if isinstance(target, dict) and isinstance(snapshot, dict):
        for key in list(target):
            if key not in snapshot:
                del target[key]
        for key, value in snapshot.items():
            if key in target and isinstance(value, (dict, list)):
                _restore_container(target[key], value)
            else:
                target[key] = copy.deepcopy(value)
    elif isinstance(target, list) and isinstance(snapshot, list):
        for index, value in enumerate(snapshot):
            if index < len(target) and isinstance(value, (dict, list)):
                _restore_container(target[index], value)
            elif index < len(target):
                target[index] = copy.deepcopy(value)
            else:
                target.append(copy.deepcopy(value))
        del target[len(snapshot) :]


def _reminder_containers(store):
    prefix = "_" if hasattr(store, "_reminders") else ""
    names = [
        "reminders",
        "tasks",
        "scheduler_outbox",
        "command_receipts",
        "reminder_occurrences",
        "reminder_delivery_attempts",
        "activation_journeys",
    ]
    return {prefix + name: getattr(store, prefix + name) for name in names}


def _rows(container):
    return container.values() if isinstance(container, dict) else container


def _delivery_state(reminder, occurrences, attempts):
    occurrence = occurrences.get(reminder["reminder_id"], {})
    related = [
        attempt
        for attempt in attempts.values()
        if attempt.get("occurrence_id") == occurrence.get("occurrence_id")
        and occurrence.get("occurrence_id") is not None
    ]
    if (
        reminder.get("telegram_message_id") is not None
        or reminder["status"] == "sent"
        or occurrence.get("provider_accepted_at")
        or any(attempt.get("provider_accepted_at") for attempt in related)
    ):
        return "accepted"
    if reminder["status"] == "sending" or occurrence.get("first_claimed_at") or related:
        return "dispatched"
    return None


async def _sync_reminder_budget(store, containers, *, legacy):
    # Compatibility with existing local atomic command wrappers: never reserve or refuse
    # participant requests, and discard obsolete ledger rows without touching Reminders.
    await store._proactive_state._discard_reminder_reservations()


def reminder_budget_transaction(method):
    """Preserve local command atomicity without admitting participant requests to a budget.

    The lock is task-reentrant for nested local Store helpers. Obsolete Reminder reservations
    are discarded without changing commitments. No provider or network calls run under it.
    """

    @wraps(method)
    async def transactional(store, *args, **kwargs):
        state = store._proactive_state
        task = asyncio.current_task()
        if getattr(state, "_reminder_transaction_owner", None) is task:
            return await method(store, *args, **kwargs)
        async with state.lock:
            containers = _reminder_containers(store)
            await _sync_reminder_budget(store, containers, legacy=True)
            snapshots = {name: copy.deepcopy(value) for name, value in containers.items()}
            reservations = copy.deepcopy(state.reservations)
            state._reminder_transaction_owner = task
            try:
                result = await method(store, *args, **kwargs)
                await _sync_reminder_budget(store, containers, legacy=False)
                return result
            except BaseException:
                for name, value in containers.items():
                    _restore_container(value, snapshots[name])
                _restore_container(state.reservations, reservations)
                raise
            finally:
                state._reminder_transaction_owner = None

    return transactional
