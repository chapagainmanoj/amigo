"""In-memory mirror of the durable Activation Journey transitions."""

from __future__ import annotations

import copy
import uuid
from collections.abc import MutableMapping
from datetime import UTC, datetime

from src.activation import ACTIVATION_LATE_AFTER, derive_activation_state
from src.commands.base import IdempotencyConflictError


def _id() -> str:
    return str(uuid.uuid4())


def _now_iso(now: datetime) -> str:
    aware = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    return aware.isoformat()


def acknowledge_terms(
    journeys: MutableMapping[str, dict],
    *,
    auth_id: str,
    policy_version: str,
    now: datetime,
) -> dict:
    """Create or idempotently return one immutable policy acknowledgement."""
    existing = journeys.get(auth_id)
    if existing and existing.get("acknowledged_at"):
        if existing["policy_version"] != policy_version:
            raise ValueError("A newer policy acknowledgement is required")
        return copy.deepcopy(existing)
    timestamp = _now_iso(now)
    row = {
        "auth_id": auth_id,
        "policy_version": policy_version,
        "acknowledged_at": timestamp,
        "profile_completed_at": None,
        "test_task_id": None,
        "test_reminder_id": None,
        "test_confirmed_at": None,
        "completed_at": None,
        "version": 1,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    journeys[auth_id] = row
    return copy.deepcopy(row)


def update_profile(
    journeys: MutableMapping[str, dict],
    users: MutableMapping[str, dict],
    *,
    auth_id: str,
    name: str,
    timezone: str,
    wake_time: str,
    sleep_time: str,
    now: datetime,
) -> dict:
    """Atomically apply the paired profile and advance durable progress."""
    journey = journeys.get(auth_id)
    if not journey or not journey.get("acknowledged_at"):
        raise ValueError("Activation limits must be acknowledged first")
    if journey.get("test_task_id"):
        raise ValueError("Activation profile is locked after the test is scheduled")
    user = next(
        (candidate for candidate in users.values() if candidate.get("supabase_auth_id") == auth_id),
        None,
    )
    if not user:
        raise ValueError("Telegram must be paired first")
    timestamp = _now_iso(now)
    user.update(
        {
            "name": name,
            "timezone": timezone,
            "wake_time": wake_time,
            "sleep_time": sleep_time,
            "onboarding_step": 3,
            "onboarding_complete": False,
            "updated_at": timestamp,
        }
    )
    if not journey.get("profile_completed_at"):
        journey["profile_completed_at"] = timestamp
        journey["version"] += 1
    journey["updated_at"] = timestamp
    return {"journey": copy.deepcopy(journey), "profile": copy.deepcopy(user)}


def create_test(
    *,
    journeys: MutableMapping[str, dict],
    users: MutableMapping[str, dict],
    tasks: MutableMapping[str, dict],
    reminders: MutableMapping[str, dict],
    occurrences: MutableMapping[str, dict],
    receipts: MutableMapping[tuple[str, str], dict],
    outbox: MutableMapping[str, dict],
    user_id: str,
    idempotency_key: str,
    payload_hash: str,
    title: str,
    retry: bool,
    scheduled_time: str,
    intended_local_date: str,
    intended_local_time: str,
    intended_timezone: str,
    now: datetime,
) -> dict:
    """Apply the combined private test Task, Reminder, receipt, and outbox transition."""
    receipt_key = (user_id, idempotency_key)
    receipt = receipts.get(receipt_key)
    if receipt:
        if receipt["payload_hash"] != payload_hash:
            raise IdempotencyConflictError("Idempotency key was reused with different input")
        return copy.deepcopy(receipt["result"])

    user = users.get(user_id)
    if not user:
        raise ValueError("User not found")
    auth_id = user.get("supabase_auth_id")
    journey = journeys.get(auth_id)
    if not journey or not journey.get("profile_completed_at"):
        raise ValueError("Activation profile must be completed first")
    if user.get("timezone") != intended_timezone:
        raise ValueError("Test Reminder timezone must match the Activation profile")

    timestamp = _now_iso(now)
    task = tasks.get(journey.get("test_task_id"))
    replaced = reminders.get(journey.get("test_reminder_id"))
    effects: list[dict] = []
    if task:
        if not retry:
            raise ValueError("Activation test Reminder already exists")
        scheduled = datetime.fromisoformat(replaced["scheduled_time"]) if replaced else None
        if scheduled and scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=UTC)
        now_utc = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        retryable = bool(
            replaced
            and (
                replaced.get("status") in {"failed", "missed", "cancelled"}
                or (
                    replaced.get("status") == "pending"
                    and replaced.get("telegram_message_id") is None
                    and scheduled
                    and now_utc > scheduled.astimezone(UTC) + ACTIVATION_LATE_AFTER
                )
            )
        )
        if not retryable:
            raise ValueError("Activation test Reminder is not eligible for retry")
        if replaced["status"] in {"pending", "sending", "sent"}:
            replaced["status"] = "cancelled"
            replaced["version"] = replaced.get("version", 1) + 1
            cancel_key = f"cancel:{replaced['reminder_id']}"
            cancel_effect = outbox.get(cancel_key) or {
                "effect_id": _id(),
                "effect_key": cancel_key,
                "effect_type": "cancel",
                "user_id": user_id,
                "task_id": task["task_id"],
                "reminder_id": replaced["reminder_id"],
                "payload": {},
                "status": "pending",
                "attempts": 0,
                "worker_id": None,
                "claimed_at": None,
                "available_at": timestamp,
                "completed_at": None,
                "created_at": timestamp,
            }
            outbox[cancel_key] = cancel_effect
            effects.append(copy.deepcopy(cancel_effect))
    else:
        task_id = _id()
        task = {
            "task_id": task_id,
            "user_id": user_id,
            "title": title,
            "category": "other",
            "due_date": intended_local_date,
            "suggested_time": None,
            "actual_completion": None,
            "status": "pending",
            "deferred_count": 0,
            "source_session_id": None,
            "version": 1,
            "created_date": intended_local_date,
            "created_at": timestamp,
        }
        tasks[task_id] = task
        journey["test_task_id"] = task_id

    reminder_id = _id()
    reminder = {
        "reminder_id": reminder_id,
        "task_id": task["task_id"],
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
        "created_at": timestamp,
    }
    reminders[reminder_id] = reminder
    occurrence_id = _id()
    occurrences[reminder_id] = {
        "occurrence_id": occurrence_id,
        "reminder_id": reminder_id,
        "user_id": user_id,
        "task_id": task["task_id"],
        "evidence_class": "participant",
        "measurable": True,
        "unmeasurable_reason": None,
        "confirmed_at": timestamp,
        "scheduled_for": scheduled_time,
        "first_claimed_at": None,
        "provider_accepted_at": None,
        "terminal_at": None,
        "acknowledged_at": None,
        "cancelled_at": None,
        "created_at": timestamp,
    }
    task["due_date"] = intended_local_date
    task["version"] = task.get("version", 1) + 1

    effect_key = f"schedule:{reminder_id}"
    schedule_effect = {
        "effect_id": _id(),
        "effect_key": effect_key,
        "effect_type": "schedule",
        "user_id": user_id,
        "task_id": task["task_id"],
        "reminder_id": reminder_id,
        "payload": {
            "scheduled_time": scheduled_time,
            "telegram_chat_id": user["telegram_chat_id"],
            "task_title": task["title"],
        },
        "status": "pending",
        "attempts": 0,
        "worker_id": None,
        "claimed_at": None,
        "available_at": timestamp,
        "completed_at": None,
        "created_at": timestamp,
    }
    outbox[effect_key] = schedule_effect
    effects.append(copy.deepcopy(schedule_effect))

    journey.update(
        {
            "test_task_id": task["task_id"],
            "test_reminder_id": reminder_id,
            "test_confirmed_at": timestamp,
            "completed_at": None,
            "version": journey["version"] + 1,
            "updated_at": timestamp,
        }
    )
    result = {
        "task": copy.deepcopy(task),
        "reminder": copy.deepcopy(reminder),
        "effect_state": "queued",
        "effects": [
            {"effect_id": effect["effect_id"], "effect_type": effect["effect_type"]}
            for effect in effects
        ],
        "journey_version": journey["version"],
    }
    receipts[receipt_key] = {"payload_hash": payload_hash, "result": copy.deepcopy(result)}
    return result


def activation_state(
    *,
    journeys: MutableMapping[str, dict],
    users: MutableMapping[str, dict],
    pairing_tokens: MutableMapping[str, dict],
    tasks: MutableMapping[str, dict],
    reminders: MutableMapping[str, dict],
    occurrences: MutableMapping[str, dict],
    auth_id: str,
    now: datetime,
) -> dict:
    """Build and, only with canonical evidence, finalize Activation progress."""
    journey = journeys.get(auth_id)
    user = next(
        (candidate for candidate in users.values() if candidate.get("supabase_auth_id") == auth_id),
        None,
    )
    candidates = [
        token for token in pairing_tokens.values() if token.get("supabase_auth_id") == auth_id
    ]
    candidates.sort(key=lambda token: token["created_at"], reverse=True)
    pairing_token = candidates[0] if candidates else None
    task = tasks.get(journey.get("test_task_id")) if journey else None
    reminder = reminders.get(journey.get("test_reminder_id")) if journey else None
    occurrence = occurrences.get(reminder["reminder_id"]) if reminder else None
    state = derive_activation_state(
        auth_id=auth_id,
        journey=journey,
        user=user,
        pairing_token=pairing_token,
        task=task,
        reminder=reminder,
        occurrence=occurrence,
        now=now,
    )
    if state["completed"] and journey and not journey.get("completed_at"):
        timestamp = _now_iso(now)
        journey["completed_at"] = timestamp
        journey["updated_at"] = timestamp
        journey["version"] += 1
        state = derive_activation_state(
            auth_id=auth_id,
            journey=journey,
            user=user,
            pairing_token=pairing_token,
            task=task,
            reminder=reminder,
            occurrence=occurrence,
            now=now,
        )
    if state["completed"] and user and not user.get("onboarding_complete"):
        user["onboarding_complete"] = True
        user["updated_at"] = _now_iso(now)
    return copy.deepcopy(state)
