"""Tool execution tests."""

from datetime import timedelta

import pytest

from src.commands.base import CommandContext
from src.memory.memory_store import InMemoryStore
from src.scheduler.outbox import SchedulerOutboxWorker
from src.tools.reminders import ScheduleReminderTool
from src.tools.tasks import CreateTaskTool, UpdateTaskStatusTool
from src.utils import now_in_tz
from tests.fakes import FakeScheduler, FakeStore


def _future_hhmm(timezone: str) -> str:
    local_target = now_in_tz(timezone) + timedelta(minutes=10)
    return local_target.strftime("%H:%M")


async def test_schedule_reminder_tool_queues_and_projects_scheduler_job():
    store = FakeStore()
    scheduler = FakeScheduler()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "call mom")
    tool = ScheduleReminderTool(store, scheduler)

    result = await tool.run(
        context=CommandContext(user["user_id"], "telegram", "schedule-tool-1"),
        task=task,
        resolved_time=_future_hhmm("Asia/Kathmandu"),
        timezone="Asia/Kathmandu",
    )

    assert result["reminder"] is not None
    assert result["effect_state"] == "queued"
    assert len(store.reminders) == 1
    assert len(scheduler.scheduled) == 0

    assert await SchedulerOutboxWorker(store, scheduler).drain_once() == 1
    assert len(scheduler.scheduled) == 1
    assert scheduler.scheduled[0]["task_title"] == "call mom"


async def test_update_task_status_tool_cancels_pending_reminders():
    store = FakeStore()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "finish slides")
    reminder = await store.create_reminder(
        task["task_id"],
        user["user_id"],
        "2099-01-01T00:00:00",
    )
    tool = UpdateTaskStatusTool(store)

    result = await tool.run(
        context=CommandContext(user["user_id"], "telegram", "resolve-tool-1"),
        task_id=task["task_id"],
        status="completed",
    )

    assert result["task"]["status"] == "completed"
    assert reminder["status"] == "cancelled"
    assert result["effect_state"] == "queued"


async def test_update_task_status_tool_rejects_cross_user_task():
    store = FakeStore()
    owner = await store.create_user(123)
    intruder = await store.create_user(456)
    task = await store.create_task(owner["user_id"], "finish slides")
    reminder = await store.create_reminder(
        task["task_id"],
        owner["user_id"],
        "2099-01-01T00:00:00",
    )
    tool = UpdateTaskStatusTool(store)

    with pytest.raises(ValueError, match="Task not found"):
        await tool.run(
            context=CommandContext(intruder["user_id"], "telegram", "resolve-intruder"),
            task_id=task["task_id"],
            status="completed",
        )

    assert task["status"] == "pending"
    assert reminder["status"] == "pending"
    assert store.scheduler_outbox == {}


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_store_task_status_update_is_tenant_owned(store_factory):
    store = store_factory()
    owner = await store.create_user(123)
    intruder = await store.create_user(456)
    task = await store.create_task(owner["user_id"], "private task")

    with pytest.raises(ValueError, match="Task not found"):
        await store.update_task_status(task["task_id"], "completed", intruder["user_id"])

    owner_tasks = await store.get_today_tasks(owner["user_id"])
    assert owner_tasks[0]["status"] == "pending"


async def test_create_task_tool_persists_task():
    store = FakeStore()
    user = await store.create_user(123)
    tool = CreateTaskTool(store)

    result = await tool.run(
        context=CommandContext(
            actor_user_id=user["user_id"],
            surface="telegram",
            idempotency_key="test:create-task-tool",
        ),
        title="drink water",
        category="health",
    )

    assert len(store.tasks) == 1
    assert result["task"]["title"] == "drink water"
    assert result["task"]["category"] == "health"
    assert result["task"]["due_date"] is None
    assert await store.get_today_tasks(user["user_id"], "Asia/Kathmandu") == []
