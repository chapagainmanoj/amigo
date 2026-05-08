"""Timezone utilities — all date/time logic goes through here.

Invariant: store UTC in database, interpret in user's timezone for display/logic.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")


class Clock:
    """Single interface for app time.

    Production uses the module-level default clock. Tests can pass a fake clock
    to modules that need deterministic time.
    """

    def utc_now(self) -> datetime:
        """Naive UTC now for Supabase timestamps and APScheduler."""
        return datetime.now(UTC).replace(tzinfo=None)

    def now_in_tz(self, timezone: str) -> datetime:
        """Current time in user's timezone."""
        return datetime.now(UTC).astimezone(ZoneInfo(timezone))

    def today_in_tz(self, timezone: str) -> date:
        """Today's date in user's timezone."""
        return self.now_in_tz(timezone).date()

    def yesterday_in_tz(self, timezone: str) -> date:
        """Yesterday's date in user's timezone."""
        return self.today_in_tz(timezone) - timedelta(days=1)

    def local_time_to_utc(self, hour: int, minute: int, timezone: str) -> datetime:
        """Convert a local HH:MM today to a naive UTC datetime."""
        tz = ZoneInfo(timezone)
        local_now = datetime.now(UTC).astimezone(tz)
        local_target = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return local_target.astimezone(UTC).replace(tzinfo=None)


default_clock = Clock()


def now_in_tz(timezone: str) -> datetime:
    """Current time in user's timezone."""
    return default_clock.now_in_tz(timezone)


def today_in_tz(timezone: str) -> date:
    """Today's date in user's timezone (not server's)."""
    return default_clock.today_in_tz(timezone)


def yesterday_in_tz(timezone: str) -> date:
    """Yesterday's date in user's timezone."""
    return default_clock.yesterday_in_tz(timezone)


def midnight_in_tz(timezone: str) -> datetime:
    """Last midnight in user's timezone, returned as UTC."""
    local_now = now_in_tz(timezone)
    local_midnight = datetime.combine(local_now.date(), time.min, tzinfo=ZoneInfo(timezone))
    return local_midnight.astimezone(UTC)


def local_time_to_utc(hour: int, minute: int, timezone: str) -> datetime:
    """Convert a local HH:MM today to UTC datetime.

    Used for scheduling reminders: "remind me at 2pm" in Asia/Kathmandu
    → stored as UTC in database, fired by APScheduler in UTC.
    """
    return default_clock.local_time_to_utc(hour, minute, timezone)


def utc_now() -> datetime:
    """Naive UTC now (for Supabase timestamps)."""
    return default_clock.utc_now()


def local_day_utc_range(timezone: str, day: date | None = None) -> tuple[datetime, datetime]:
    """Return UTC start/end instants for a user's local calendar day.

    The returned datetimes are naive UTC values, matching the rest of the app's
    Supabase timestamp writes.
    """
    tz = ZoneInfo(timezone)
    local_day = day or today_in_tz(timezone)
    start_local = datetime.combine(local_day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(UTC).replace(tzinfo=None),
        end_local.astimezone(UTC).replace(tzinfo=None),
    )
