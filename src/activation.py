"""Dashboard-first Activation Journey rules and read-model derivation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

ACTIVATION_POLICY_VERSION = "2026-08-29"
ACTIVATION_TEST_TASK_TITLE = "Private Amigo test reminder"
ACTIVATION_TEST_DELAY = timedelta(minutes=2)
ACTIVATION_TEST_EARLIEST = timedelta(seconds=60)
ACTIVATION_TEST_LATEST = timedelta(minutes=5)
ACTIVATION_LATE_AFTER = timedelta(seconds=30)


def validate_preferred_name(value: str) -> str:
    """Normalize a display name without changing its chosen capitalization."""
    name = " ".join(value.strip().split())
    if not 1 <= len(name) <= 80 or any(ord(character) < 32 for character in name):
        raise ValueError("Preferred name must be between 1 and 80 visible characters")
    return name


def validate_timezone(value: str) -> str:
    """Require an explicit canonical-looking IANA timezone (or UTC)."""
    timezone = value.strip()
    if timezone != "UTC" and "/" not in timezone:
        raise ValueError("Use an IANA timezone such as America/Toronto or Asia/Kathmandu")
    try:
        ZoneInfo(timezone)
    except (KeyError, ValueError):
        raise ValueError("Use a valid IANA timezone") from None
    return timezone


def validate_quiet_hours(wake_time: str, sleep_time: str) -> tuple[str, str]:
    """Validate the beta quiet-hours boundary represented by wake and sleep times."""
    try:
        wake = datetime.strptime(wake_time, "%H:%M").time()
        sleep = datetime.strptime(sleep_time, "%H:%M").time()
    except ValueError:
        raise ValueError("Quiet-hour times must use 24-hour HH:MM format") from None
    if wake == sleep:
        raise ValueError("Wake and quiet-hour start times must differ")
    return wake.strftime("%H:%M"), sleep.strftime("%H:%M")


def proposed_test_time(timezone: str, now: datetime) -> dict[str, str]:
    """Return the exact two-minute test Reminder proposal shown before confirmation."""
    zone = ZoneInfo(validate_timezone(timezone))
    aware_now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    scheduled = (aware_now + ACTIVATION_TEST_DELAY).replace(microsecond=0)
    local = scheduled.astimezone(zone)
    return {
        "scheduled_at": scheduled.isoformat(),
        "local_date": local.date().isoformat(),
        "local_time": local.time().replace(microsecond=0).isoformat(),
        "timezone": timezone,
    }


def validate_test_time(scheduled_at: datetime, timezone: str, now: datetime) -> dict[str, str]:
    """Validate the exact confirmed test time and return canonical scheduling fields."""
    zone = ZoneInfo(validate_timezone(timezone))
    if scheduled_at.tzinfo is None:
        raise ValueError("Test Reminder time must include a timezone offset")
    aware_now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    scheduled = scheduled_at.astimezone(UTC)
    delay = scheduled - aware_now
    if delay < ACTIVATION_TEST_EARLIEST or delay > ACTIVATION_TEST_LATEST:
        raise ValueError("Test Reminder must be confirmed between one and five minutes ahead")
    local = scheduled.astimezone(zone)
    return {
        "scheduled_time": scheduled.isoformat(),
        "intended_local_date": local.date().isoformat(),
        "intended_local_time": local.time().replace(microsecond=0).isoformat(),
        "intended_timezone": timezone,
    }


def _as_utc(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def derive_activation_state(
    *,
    auth_id: str,
    journey: dict | None,
    user: dict | None,
    pairing_token: dict | None,
    task: dict | None,
    reminder: dict | None,
    occurrence: dict | None,
    now: datetime,
) -> dict:
    """Derive the first incomplete step only from durable canonical evidence."""
    now_utc = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
    acknowledged = bool(journey and journey.get("acknowledged_at"))
    profile_complete = bool(journey and journey.get("profile_completed_at") and user)

    pairing_status = "none"
    if pairing_token:
        if pairing_token.get("invalidated_at"):
            pairing_status = "replaced"
        elif pairing_token.get("consumed"):
            pairing_status = "used"
        elif (_as_utc(pairing_token.get("expires_at")) or now_utc) <= now_utc:
            pairing_status = "expired"
        else:
            pairing_status = "active"

    delivered = bool(
        reminder
        and (
            reminder.get("telegram_message_id") is not None
            or (occurrence and occurrence.get("provider_accepted_at"))
        )
    )
    resolution = None
    if task and reminder:
        if task.get("status") == "completed" and reminder.get("status") == "acknowledged":
            resolution = "done"
        elif task.get("status") == "skipped" and reminder.get("status") == "acknowledged":
            resolution = "skip"
        elif (
            reminder.get("status") == "acknowledged"
            and task.get("status") == "pending"
            and (task.get("deferred_count") or 0) > 0
        ):
            resolution = "later"

    scheduled_at = _as_utc(reminder.get("scheduled_time") if reminder else None)
    delivery_state = "not_scheduled"
    can_retry = False
    if reminder:
        if delivered:
            delivery_state = "delivered"
        elif reminder.get("status") == "failed":
            delivery_state = "failed"
            can_retry = True
        elif reminder.get("status") == "missed":
            delivery_state = "missed"
            can_retry = True
        elif reminder.get("status") == "cancelled":
            delivery_state = "cancelled"
            can_retry = True
        elif (
            reminder.get("status") == "pending"
            and scheduled_at
            and now_utc > scheduled_at + ACTIVATION_LATE_AFTER
        ):
            delivery_state = "late"
            can_retry = True
        else:
            delivery_state = "scheduled"

    complete = delivered and resolution in {"done", "skip", "later"}
    if not acknowledged:
        step = "limits"
    elif not user:
        step = "telegram"
    elif not profile_complete:
        step = "profile"
    elif not reminder:
        step = "test_reminder"
    elif not complete:
        step = "resolve"
    else:
        step = "dashboard"

    return {
        "policy_version": journey.get("policy_version") if journey else None,
        "acknowledged_at": journey.get("acknowledged_at") if journey else None,
        "journey_version": journey.get("version", 0) if journey else 0,
        "step": step,
        "completed": complete,
        "completed_at": journey.get("completed_at") if journey else None,
        "paired": bool(user),
        "pairing": {
            "status": pairing_status,
            "expires_at": pairing_token.get("expires_at") if pairing_token else None,
        },
        "profile_complete": profile_complete,
        "profile": (
            {
                "name": user.get("name"),
                "timezone": user.get("timezone"),
                "wake_time": user.get("wake_time"),
                "sleep_time": user.get("sleep_time"),
            }
            if user
            else None
        ),
        "test": {
            "task": (
                {
                    "title": task.get("title"),
                    "status": task.get("status"),
                    "due_date": task.get("due_date"),
                    "version": task.get("version"),
                    "deferred_count": task.get("deferred_count") or 0,
                }
                if task
                else None
            ),
            "reminder": (
                {
                    "scheduled_time": reminder.get("scheduled_time"),
                    "intended_local_date": reminder.get("intended_local_date"),
                    "intended_local_time": reminder.get("intended_local_time"),
                    "intended_timezone": reminder.get("intended_timezone"),
                    "status": reminder.get("status"),
                }
                if reminder
                else None
            ),
            "delivered": delivered,
            "delivery_state": delivery_state,
            "resolution": resolution,
            "can_retry": can_retry,
        },
        "generated_at": now_utc.isoformat(),
    }
