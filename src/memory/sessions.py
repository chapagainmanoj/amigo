"""Session boundary logic — type-aware + time-aware."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from src.utils import Clock, default_clock

if TYPE_CHECKING:
    from src.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages session lifecycle: open, close, timeout detection.

    Rules:
    - 2hr inactivity gap (configurable per user) closes a session
    - Midnight always closes regardless
    - Single-message task updates append to previous session
    - Explicit closers ("goodnight", "done for today") close immediately
    """

    # Messages that signal explicit session close
    CLOSE_SIGNALS = {"goodnight", "done for today", "going to sleep", "bye", "good night"}

    def __init__(self, store: MemoryStore, clock: Clock = default_clock):
        self.store = store
        self.clock = clock

    async def get_or_create_session(
        self, user_id: str, timeout_minutes: int = 120, timezone: str = "UTC"
    ) -> tuple[dict, bool]:
        """Get active session or create a new one.

        Args:
            user_id: User identifier
            timeout_minutes: Inactivity gap before session closes
            timezone: User's timezone for midnight boundary check

        Returns:
            (session_dict, is_new_session)
        """
        active = await self.store.get_active_session(user_id)

        if active:
            last_activity = datetime.fromisoformat(active["last_activity_at"])
            now = self.clock.utc_now()
            gap = now - last_activity

            # Check midnight boundary in USER's timezone
            user_now = self.clock.now_in_tz(timezone)
            last_activity_local = last_activity.replace(tzinfo=ZoneInfo("UTC")).astimezone(
                ZoneInfo(timezone)
            )

            if last_activity_local.date() < user_now.date():
                logger.info("Closing session %s — midnight boundary", active["session_id"])
                await self.store.close_session(active["session_id"])
                session = await self.store.create_session(user_id, "morning_planning")
                return session, True

            # Check inactivity timeout
            if gap > timedelta(minutes=timeout_minutes):
                logger.info(
                    "Closing session %s — %d min inactive",
                    active["session_id"],
                    gap.total_seconds() // 60,
                )
                await self.store.close_session(active["session_id"])
                session = await self.store.create_session(user_id)
                return session, True

            # Session still active — touch it
            await self.store.touch_session(active["session_id"])
            return active, False

        # No active session — determine type from the user's local day.
        is_first_today = not await self.store.has_session_on_local_day(user_id, timezone)
        session_type = self.classify_session_type(
            self.clock.now_in_tz(timezone).hour, is_first_today
        )
        session = await self.store.create_session(user_id, session_type)
        return session, True

    async def should_close(self, message: str) -> bool:
        """Check if user message signals explicit session close."""
        normalized = message.lower().strip()
        return any(signal in normalized for signal in self.CLOSE_SIGNALS)

    def classify_session_type(self, hour: int, is_first_today: bool) -> str:
        """Determine session type based on time and context."""
        if is_first_today:
            return "morning_planning"
        if hour >= 20:
            return "evening"
        return "check_in"
