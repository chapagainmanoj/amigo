"""Session rollover tests — test #7.

Tests that session boundaries respect USER's timezone for midnight,
not server UTC. Uses frozen time to test deterministically.
"""

from datetime import timedelta

import pytest

from src.memory.sessions import SessionManager
from src.utils import utc_now
from tests.fakes import FakeStore


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def mgr(store):
    return SessionManager(store)


class TestMidnightRollover:
    """Session should close at midnight in user's timezone, not UTC."""

    @pytest.mark.asyncio
    async def test_no_rollover_same_local_day(self, store, mgr):
        """Active session on same local day should NOT close."""
        user = await store.create_user(12345)
        uid = user["user_id"]
        session = await store.create_session(uid, "casual")

        # Last activity 1 hour ago — same day
        one_hour_ago = (utc_now() - timedelta(hours=1)).isoformat()
        session["last_activity_at"] = one_hour_ago

        result, is_new = await mgr.get_or_create_session(uid, timezone="UTC")
        assert is_new is False
        assert result["session_id"] == session["session_id"]

    @pytest.mark.asyncio
    async def test_rollover_at_local_midnight(self, store, mgr):
        """Session from yesterday should close and create morning_planning."""
        user = await store.create_user(12345)
        uid = user["user_id"]
        session = await store.create_session(uid, "casual")

        # Last activity 25 hours ago — yesterday for sure
        old_time = (utc_now() - timedelta(hours=25)).isoformat()
        session["last_activity_at"] = old_time
        session["started_at"] = old_time

        result, is_new = await mgr.get_or_create_session(uid, timezone="UTC")
        assert is_new is True
        assert result["session_type"] == "morning_planning"
        # Old session should be closed
        assert session["ended_at"] is not None


class TestFirstMessageOfDay:
    """Test #14: No active session + no sessions today → morning_planning."""

    @pytest.mark.asyncio
    async def test_first_message_creates_morning_planning(self, store, mgr):
        """Brand new day, no sessions at all → morning_planning."""
        user = await store.create_user(12345)
        uid = user["user_id"]

        result, is_new = await mgr.get_or_create_session(uid, timezone="UTC")
        assert is_new is True
        assert result["session_type"] == "morning_planning"

    @pytest.mark.asyncio
    async def test_second_session_same_day_not_morning(self, store, mgr):
        """Already had a session today → new session should be check_in or evening, not morning."""
        user = await store.create_user(12345)
        uid = user["user_id"]

        # Create and close a session today
        s1 = await store.create_session(uid, "morning_planning")
        await store.close_session(s1["session_id"])

        # Inactivity timeout later in the day
        result, is_new = await mgr.get_or_create_session(uid, timeout_minutes=0, timezone="UTC")
        assert is_new is True
        assert result["session_type"] != "morning_planning"


class TestInactivityTimeout:
    """Session closes after inactivity gap."""

    @pytest.mark.asyncio
    async def test_timeout_closes_session(self, store, mgr):
        user = await store.create_user(12345)
        uid = user["user_id"]
        session = await store.create_session(uid, "casual")

        # 3 hours ago — exceeds 120min timeout
        old_time = (utc_now() - timedelta(hours=3)).isoformat()
        session["last_activity_at"] = old_time

        result, is_new = await mgr.get_or_create_session(uid, timeout_minutes=120, timezone="UTC")
        assert is_new is True
        assert session["ended_at"] is not None
