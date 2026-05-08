"""Reminder snooze logic tests."""



class TestSnoozeLogic:
    """Test the snooze delay escalation: 1hr → 30min → defer."""

    def _snooze_delay(self, snooze_count: int) -> int | None:
        """Replicate the snooze logic from handlers."""
        delays = [60, 30]
        if snooze_count >= len(delays):
            return None  # defer
        return delays[snooze_count]

    def test_first_snooze_is_60min(self):
        assert self._snooze_delay(0) == 60

    def test_second_snooze_is_30min(self):
        assert self._snooze_delay(1) == 30

    def test_third_snooze_defers(self):
        assert self._snooze_delay(2) is None

    def test_beyond_max_defers(self):
        assert self._snooze_delay(5) is None
