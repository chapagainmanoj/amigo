"""Explicit Reminder date/time, timezone, ambiguity, and confirmation tests."""

from datetime import UTC, datetime

import pytest

from src.agent.agent import (
    AgentDeps,
    _resolution_block_message,
    _schedule_resolved_reminder,
)
from src.time_resolution import resolve_reminder_time
from src.utils import Clock
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


class FixedClock(Clock):
    def __init__(self, current: datetime):
        self.current = current

    def utc_now(self) -> datetime:
        return self.current


@pytest.mark.parametrize(
    ("expression", "reason_fragment"),
    [
        ("at 8", "AM or PM"),
        ("tomorrow", "exact time"),
        ("after lunch", "fuzzy period"),
        ("tomorrow yesterday at 3pm", "contradictory"),
        ("2026-08-31 15:00", "already passed"),
    ],
)
def test_ambiguous_or_invalid_expressions_require_clarification(expression, reason_fragment):
    result = resolve_reminder_time(
        expression,
        "UTC",
        clock=FixedClock(datetime(2026, 8, 31, 16, 0)),
    )

    assert result.clarification_required is True
    assert result.utc_instant is None
    assert reason_fragment in result.reason


def test_unambiguous_relative_time_can_schedule_directly_with_exact_receipt():
    result = resolve_reminder_time(
        "in 30 minutes",
        "Asia/Kathmandu",
        clock=FixedClock(datetime(2026, 8, 31, 4, 0)),
    )

    assert result.clarification_required is False
    assert result.confirmation_required is False
    assert result.local_date.isoformat() == "2026-08-31"
    assert result.local_time.isoformat() == "10:15:00"
    assert result.utc_instant == datetime(2026, 8, 31, 4, 30, tzinfo=UTC)
    assert result.exact_label == "2026-08-31 at 10:15 Asia/Kathmandu"


def test_nonexistent_dst_wall_time_requires_another_choice():
    result = resolve_reminder_time(
        "2026-03-08 02:30",
        "America/New_York",
        clock=FixedClock(datetime(2026, 1, 1, 12, 0)),
    )

    assert result.clarification_required is True
    assert "does not exist" in result.reason


def test_repeated_dst_wall_time_uses_earlier_occurrence_unless_selected_otherwise():
    earlier = resolve_reminder_time(
        "2026-11-01 01:30",
        "America/New_York",
        clock=FixedClock(datetime(2026, 1, 1, 12, 0)),
    )
    later = resolve_reminder_time(
        "2026-11-01 01:30",
        "America/New_York",
        clock=FixedClock(datetime(2026, 1, 1, 12, 0)),
        prefer_later_fold=True,
    )

    assert earlier.repeated_wall_time is True
    assert earlier.utc_instant == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert later.utc_instant == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    assert earlier.confirmation_required is True


@pytest.mark.parametrize(
    ("timezone", "expression", "expected_utc"),
    [
        (
            "Asia/Kathmandu",
            "2026-09-01 09:15",
            datetime(2026, 9, 1, 3, 30, tzinfo=UTC),
        ),
        (
            "America/St_Johns",
            "2026-09-01 09:15",
            datetime(2026, 9, 1, 11, 45, tzinfo=UTC),
        ),
        (
            "Pacific/Honolulu",
            "2026-09-01 00:00",
            datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        ),
    ],
)
def test_half_hour_both_offset_directions_and_midnight(timezone, expression, expected_utc):
    result = resolve_reminder_time(
        expression,
        timezone,
        clock=FixedClock(datetime(2026, 8, 1, 12, 0)),
    )

    assert result.clarification_required is False
    assert result.confirmation_required is True
    assert result.utc_instant == expected_utc


def test_explicit_quiet_hour_request_requires_one_time_confirmation():
    result = resolve_reminder_time(
        "2026-09-01 23:30",
        "UTC",
        clock=FixedClock(datetime(2026, 8, 31, 12, 0)),
        wake_time="07:30",
        sleep_time="23:00",
    )

    assert result.quiet_hours is True
    assert result.confirmation_required is True
    assert "quiet hours" in result.reason


def test_automatic_suggestion_moves_to_wake_time_instead_of_quiet_hours():
    result = resolve_reminder_time(
        "2026-09-01 23:30",
        "UTC",
        clock=FixedClock(datetime(2026, 8, 31, 12, 0)),
        wake_time="07:30",
        sleep_time="23:00",
        automatic_suggestion=True,
    )

    assert result.quiet_hours is False
    assert result.quiet_hours_adjusted is True
    assert result.local_date.isoformat() == "2026-09-02"
    assert result.local_time.isoformat() == "07:30:00"
    assert result.confirmation_required is True


async def test_confirmation_boundary_prevents_mutation_and_saved_utc_stays_anchored():
    store = FakeStore()
    user = await store.create_user(123)
    await store.update_user(
        user["user_id"],
        {"timezone": "Asia/Kathmandu", "onboarding_complete": True},
    )
    task = await store.create_task(user["user_id"], "Confirm flight")
    resolution = resolve_reminder_time(
        "2026-09-01 09:15",
        "Asia/Kathmandu",
        clock=FixedClock(datetime(2026, 8, 31, 12, 0)),
    )
    deps = AgentDeps(
        store=store,
        scheduler=FakeScheduler(),
        channel=FakeChannel(),
        user=user,
        session_id="session-1",
        chat_id=123,
        timezone="Asia/Kathmandu",
        turn_id="confirm-time",
    )

    prompt = _resolution_block_message(resolution, confirmed_interpretation=None)
    assert "Please confirm" in prompt
    assert "Nothing has been scheduled" in prompt
    assert store.reminders == []
    assert store.scheduler_outbox == {}

    mismatch = _resolution_block_message(
        resolution,
        confirmed_interpretation="2026-09-01 at 09:15 UTC",
    )
    assert "Please confirm" in mismatch
    assert store.reminders == []

    assert (
        _resolution_block_message(
            resolution,
            confirmed_interpretation=resolution.exact_label,
        )
        is None
    )

    exact = await _schedule_resolved_reminder(deps, task, resolution)
    saved_utc = store.reminders[0]["scheduled_time"]
    await store.update_user(user["user_id"], {"timezone": "America/New_York"})

    assert exact == "2026-09-01 at 09:15 Asia/Kathmandu"
    assert saved_utc == "2026-09-01T03:30:00+00:00"
    assert store.reminders[0]["scheduled_time"] == saved_utc
