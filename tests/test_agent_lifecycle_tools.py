"""Agent Tool regressions found by the Gate A evaluation probes."""

from datetime import UTC, datetime
from types import SimpleNamespace

from src.agent.agent import (
    AgentDeps,
    apply_later,
    create_task,
    schedule_reminder,
)
from src.memory.memory_store import InMemoryStore
from src.utils import Clock
from tests.fakes import FakeChannel, FakeScheduler


class FixedClock(Clock):
    def __init__(self, value: datetime):
        self.value = value

    def utc_now(self) -> datetime:
        return self.value


async def _deps():
    store = InMemoryStore()
    user = await store.create_user(123)
    user = await store.update_user(
        user["user_id"],
        {
            "name": "Dev",
            "timezone": "Asia/Kathmandu",
            "wake_time": "07:30",
            "sleep_time": "23:00",
            "onboarding_complete": True,
        },
    )
    session = await store.create_session(user["user_id"])
    deps = AgentDeps(
        store=store,
        scheduler=FakeScheduler(),
        channel=FakeChannel(),
        user=user,
        session_id=session["session_id"],
        chat_id=123,
        timezone="Asia/Kathmandu",
        turn_id="turn-1",
        clock=FixedClock(datetime(2026, 9, 1, 4, 15)),
    )
    return store, deps


async def test_confirmation_without_original_expression_creates_nothing():
    store, deps = await _deps()

    result = await create_task(
        SimpleNamespace(deps=deps),
        "Send invoice",
        confirmed_reminder_time="2026-09-02 at 15:00 Asia/Kathmandu",
    )

    assert "No Task or Reminder was created" in result
    assert store._tasks == {}
    assert store._reminders == {}


async def test_agent_reschedule_replaces_existing_reminder():
    store, deps = await _deps()
    task = await store.create_task(deps.user["user_id"], "Prepare demo")
    old = await store.create_reminder(
        task["task_id"],
        deps.user["user_id"],
        datetime(2026, 9, 2, 4, 15, tzinfo=UTC).isoformat(),
    )

    result = await schedule_reminder(
        SimpleNamespace(deps=deps),
        task["task_id"],
        "in 90 minutes",
    )

    pending = await store.get_pending_reminders(deps.user["user_id"])
    assert "Reminder scheduled" in result
    assert len(pending) == 1
    assert pending[0]["reminder_id"] != old["reminder_id"]
    assert store._reminders[old["reminder_id"]]["status"] == "cancelled"


async def test_agent_later_uses_canonical_replacement_policy():
    store, deps = await _deps()
    task = await store.create_task(deps.user["user_id"], "Reply to email")
    old = await store.create_reminder(
        task["task_id"],
        deps.user["user_id"],
        datetime(2026, 9, 1, 5, 0, tzinfo=UTC).isoformat(),
    )

    result = await apply_later(SimpleNamespace(deps=deps), old["reminder_id"])

    pending = await store.get_pending_reminders(deps.user["user_id"])
    assert "Next reminder" in result
    assert len(pending) == 1
    assert pending[0]["reminder_id"] != old["reminder_id"]
    assert store._reminders[old["reminder_id"]]["status"] == "acknowledged"
