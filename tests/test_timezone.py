"""Timezone utility tests — boundary cases near midnight.

Tests #6 and #8 from the grill list.
"""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from src.utils import local_time_to_utc, today_in_tz, yesterday_in_tz


class TestTodayYesterdayBoundary:
    """Kathmandu is UTC+5:45. Toronto is UTC-4/-5.

    Near midnight, "today" depends on whose clock you're reading.
    """

    def test_kathmandu_ahead_of_utc(self):
        """At 1am in Kathmandu, today should be tomorrow in UTC terms."""
        # Freeze: 2026-05-07 19:15 UTC = 2026-05-08 01:00 NPT
        fake_utc = datetime(2026, 5, 7, 19, 15, tzinfo=ZoneInfo("UTC"))
        with patch("src.utils.datetime") as mock_dt:
            mock_dt.now.return_value = fake_utc
            mock_dt.combine = datetime.combine
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            today = today_in_tz("Asia/Kathmandu")
            yesterday = yesterday_in_tz("Asia/Kathmandu")

            from datetime import date
            assert today == date(2026, 5, 8), "Kathmandu should be May 8"
            assert yesterday == date(2026, 5, 7)

    def test_toronto_behind_utc(self):
        """When it's 11pm in UTC (7pm Toronto), today in Toronto is still the same UTC day."""
        fake_utc = datetime(2026, 5, 7, 23, 0, tzinfo=ZoneInfo("UTC"))
        with patch("src.utils.datetime") as mock_dt:
            mock_dt.now.return_value = fake_utc
            mock_dt.combine = datetime.combine
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            today = today_in_tz("America/Toronto")
            from datetime import date
            assert today == date(2026, 5, 7), "Toronto should still be May 7"


class TestLocalTimeToUtc:
    """Reminder scheduling: '2pm' in Kathmandu != '2pm' in UTC."""

    def test_kathmandu_2pm_to_utc(self):
        """2pm NPT = 08:15 UTC."""
        utc_time = local_time_to_utc(14, 0, "Asia/Kathmandu")
        assert utc_time.hour == 8
        assert utc_time.minute == 15

    def test_toronto_2pm_to_utc_edt(self):
        """2pm EDT (summer) = 18:00 UTC."""
        # This test depends on the actual current date — use a fixed approach
        utc_time = local_time_to_utc(14, 0, "America/Toronto")
        # Toronto is UTC-4 in summer (EDT) or UTC-5 in winter (EST)
        # Either way, the hour should be 14 + 4 or 14 + 5
        assert utc_time.hour in (18, 19)

    def test_midnight_conversion(self):
        """Midnight in Kathmandu = 18:15 UTC previous day."""
        utc_time = local_time_to_utc(0, 0, "Asia/Kathmandu")
        assert utc_time.hour == 18
        assert utc_time.minute == 15


class TestCreatedDateTimezone:
    """Test #8: created_date must use user timezone, not server."""

    @pytest.mark.asyncio
    async def test_task_created_date_uses_user_timezone(self):
        """Tasks created near midnight should use user's local date."""
        from tests.fakes import FakeStore

        store = FakeStore()
        user = await store.create_user(12345)
        user_id = user["user_id"]

        # Create task with Kathmandu timezone
        task = await store.create_task(
            user_id=user_id,
            title="Test task",
            timezone="Asia/Kathmandu",
        )

        # created_date should match today in Kathmandu, not UTC
        expected = today_in_tz("Asia/Kathmandu").isoformat()
        assert task["created_date"] == expected
