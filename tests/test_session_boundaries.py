"""Session boundary tests."""

from unittest.mock import MagicMock

import pytest

from src.memory.sessions import SessionManager


class TestSessionClose:
    """Test explicit session close detection."""

    def setup_method(self):
        self.store = MagicMock()
        self.mgr = SessionManager(self.store)

    @pytest.mark.asyncio
    async def test_goodnight_closes_session(self):
        assert await self.mgr.should_close("goodnight") is True

    @pytest.mark.asyncio
    async def test_good_night_closes_session(self):
        assert await self.mgr.should_close("good night!") is True

    @pytest.mark.asyncio
    async def test_done_for_today_closes(self):
        assert await self.mgr.should_close("done for today") is True

    @pytest.mark.asyncio
    async def test_normal_message_does_not_close(self):
        assert await self.mgr.should_close("what's on my list?") is False

    @pytest.mark.asyncio
    async def test_bye_closes(self):
        assert await self.mgr.should_close("bye!") is True


class TestSessionTypeClassification:
    """Test session type detection."""

    def setup_method(self):
        self.store = MagicMock()
        self.mgr = SessionManager(self.store)

    def test_morning_planning(self):
        assert self.mgr.classify_session_type(7, is_first_today=True) == "morning_planning"

    def test_first_message_always_morning(self):
        assert self.mgr.classify_session_type(15, is_first_today=True) == "morning_planning"

    def test_evening_session(self):
        assert self.mgr.classify_session_type(21, is_first_today=False) == "evening"

    def test_midday_checkin(self):
        assert self.mgr.classify_session_type(14, is_first_today=False) == "check_in"
