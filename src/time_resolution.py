"""Deterministic Reminder time resolution with explicit safety boundaries."""

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser

from src.utils import Clock, default_clock

_FUZZY_PERIODS = re.compile(
    r"\b(breakfast|lunch|dinner|tonight|morning|afternoon|evening|after work)\b",
    re.IGNORECASE,
)
_RELATIVE = re.compile(
    r"^in\s+(\d+)\s+(minute|minutes|hour|hours|day|days)$",
    re.IGNORECASE,
)
_BARE_HOUR = re.compile(r"^(?:at\s+)?(?:[01]?\d|2[0-3])$", re.IGNORECASE)
_HAS_TIME = re.compile(
    r"(?:\b\d{1,2}:\d{2}\b|\b\d{1,2}\s*(?:am|pm)\b|\bnoon\b|\bmidnight\b)",
    re.IGNORECASE,
)
_DATE_SIGNAL = re.compile(
    r"\b(today|tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{4}-\d{2}-\d{2})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TimeResolution:
    """Full interpretation or a reason persistence must pause."""

    expression: str
    timezone: str
    local_date: date | None
    local_time: time | None
    utc_instant: datetime | None
    confidence: Literal["high", "medium", "low"]
    clarification_required: bool
    confirmation_required: bool
    reason: str | None = None
    repeated_wall_time: bool = False
    quiet_hours: bool = False
    quiet_hours_adjusted: bool = False

    @property
    def exact_label(self) -> str | None:
        if self.local_date is None or self.local_time is None:
            return None
        return (
            f"{self.local_date.isoformat()} at {self.local_time.strftime('%H:%M')} "
            f"{self.timezone}"
        )


def _blocked(expression: str, timezone: str, reason: str) -> TimeResolution:
    return TimeResolution(
        expression=expression,
        timezone=timezone,
        local_date=None,
        local_time=None,
        utc_instant=None,
        confidence="low",
        clarification_required=True,
        confirmation_required=False,
        reason=reason,
    )


def _parse_profile_time(value: str | time | None) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    return time.fromisoformat(value)


def _in_quiet_hours(candidate: time, sleep: time, wake: time) -> bool:
    if sleep == wake:
        return False
    if sleep < wake:
        return sleep <= candidate < wake
    return candidate >= sleep or candidate < wake


def resolve_reminder_time(
    expression: str,
    timezone: str,
    *,
    clock: Clock = default_clock,
    wake_time: str | time | None = "07:30",
    sleep_time: str | time | None = "23:00",
    prefer_later_fold: bool = False,
    automatic_suggestion: bool = False,
) -> TimeResolution:
    """Resolve an expression without silently inventing missing date/time intent."""
    text = " ".join(expression.strip().split())
    if not text:
        return _blocked(text, timezone, "Tell me the date and time you want.")
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return _blocked(text, timezone, "Choose a valid IANA timezone first.")

    lowered = text.lower()
    if ("tomorrow" in lowered and "yesterday" in lowered) or (
        "am" in lowered and "pm" in lowered
    ):
        return _blocked(text, timezone, "The time contains contradictory details.")
    if _FUZZY_PERIODS.search(text):
        return _blocked(
            text,
            timezone,
            "Choose an exact wall time instead of a fuzzy period.",
        )
    if _BARE_HOUR.fullmatch(text):
        return _blocked(text, timezone, "Specify AM or PM and the intended date.")
    if _DATE_SIGNAL.search(text) and not _HAS_TIME.search(text):
        return _blocked(text, timezone, "That date still needs an exact time.")

    local_now = clock.utc_now().replace(tzinfo=UTC).astimezone(tz)
    relative = _RELATIVE.fullmatch(text)
    if relative:
        amount = int(relative.group(1))
        if amount < 1:
            return _blocked(text, timezone, "Choose a future relative time.")
        unit = relative.group(2).lower()
        if unit.startswith("minute"):
            candidate = local_now + timedelta(minutes=amount)
        elif unit.startswith("hour"):
            candidate = local_now + timedelta(hours=amount)
        else:
            candidate = local_now + timedelta(days=amount)
        confirmation_required = False
        confidence: Literal["high", "medium", "low"] = "high"
        repeated = False
    else:
        parsed = dateparser.parse(
            text,
            settings={
                "TIMEZONE": timezone,
                "RETURN_AS_TIMEZONE_AWARE": False,
                "PREFER_DATES_FROM": "current_period",
                "RELATIVE_BASE": local_now.replace(tzinfo=None),
            },
        )
        if parsed is None:
            return _blocked(text, timezone, "I could not resolve that date and time.")
        naive = parsed.replace(tzinfo=None)
        earlier = naive.replace(tzinfo=tz, fold=0)
        later = naive.replace(tzinfo=tz, fold=1)
        if earlier.astimezone(UTC).astimezone(tz).replace(tzinfo=None) != naive:
            return _blocked(
                text,
                timezone,
                "That local wall time does not exist because of a daylight-saving change.",
            )
        repeated = earlier.utcoffset() != later.utcoffset()
        candidate = later if repeated and prefer_later_fold else earlier
        confirmation_required = True
        confidence = "medium" if repeated else "high"

    if candidate <= local_now:
        return _blocked(
            text,
            timezone,
            "That time has already passed; choose a future date and time.",
        )

    wake = _parse_profile_time(wake_time)
    sleep = _parse_profile_time(sleep_time)
    quiet = bool(
        wake is not None
        and sleep is not None
        and _in_quiet_hours(candidate.timetz().replace(tzinfo=None), sleep, wake)
    )
    quiet_adjusted = False
    if quiet and automatic_suggestion and wake is not None and sleep is not None:
        wake_day = candidate.date()
        candidate_time = candidate.timetz().replace(tzinfo=None)
        if sleep > wake and candidate_time >= sleep:
            wake_day += timedelta(days=1)
        candidate = datetime.combine(wake_day, wake, tzinfo=tz)
        quiet = False
        quiet_adjusted = True
        confirmation_required = True
    elif quiet:
        confirmation_required = True

    reason = None
    if repeated:
        reason = "This wall time occurs twice; the earlier occurrence is selected."
    if quiet:
        reason = "This time is inside your quiet hours and needs one-time confirmation."
    elif quiet_adjusted:
        reason = "The automatic suggestion was moved to your wake time to avoid quiet hours."

    return TimeResolution(
        expression=text,
        timezone=timezone,
        local_date=candidate.date(),
        local_time=candidate.timetz().replace(tzinfo=None),
        utc_instant=candidate.astimezone(UTC),
        confidence=confidence,
        clarification_required=False,
        confirmation_required=confirmation_required,
        reason=reason,
        repeated_wall_time=repeated,
        quiet_hours=quiet,
        quiet_hours_adjusted=quiet_adjusted,
    )
