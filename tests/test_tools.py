"""Tool execution tests."""

from datetime import timedelta

from src.agent.models import ToolCall
from src.tools import ToolExecutionContext, ToolExecutor
from src.tools.reminders import CancelRemindersTool, ScheduleReminderTool
from src.tools.tasks import UpdateTaskStatusTool
from src.utils import now_in_tz
from tests.fakes import FakeScheduler, FakeStore


def _future_hhmm(timezone: str) -> str:
    local_target = now_in_tz(timezone) + timedelta(minutes=10)
    return local_target.strftime("%H:%M")


async def test_schedule_reminder_tool_creates_reminder_and_schedules_job():
    store = FakeStore()
    scheduler = FakeScheduler()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "call mom")
    tool = ScheduleReminderTool(store, scheduler)

    result = await tool.run(
        user_id=user["user_id"],
        task=task,
        resolved_time=_future_hhmm("Asia/Kathmandu"),
        timezone="Asia/Kathmandu",
        chat_id=123,
    )

    assert result["reminder"] is not None
    assert len(store.reminders) == 1
    assert len(scheduler.scheduled) == 1
    assert scheduler.scheduled[0]["task_title"] == "call mom"


async def test_update_task_status_tool_cancels_pending_reminders():
    store = FakeStore()
    scheduler = FakeScheduler()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "finish slides")
    reminder = await store.create_reminder(
        task["task_id"],
        user["user_id"],
        "2099-01-01T00:00:00",
    )
    tool = UpdateTaskStatusTool(store, CancelRemindersTool(store, scheduler))

    result = await tool.run(
        task_id=task["task_id"],
        status="done",
        user_id=user["user_id"],
    )

    assert result["task"]["status"] == "done"
    assert reminder["status"] == "acknowledged"
    assert scheduler.cancelled == [reminder["reminder_id"]]


async def test_tool_executor_passes_created_task_to_schedule_reminder():
    store = FakeStore()
    scheduler = FakeScheduler()
    user = await store.create_user(123)
    executor = ToolExecutor(store, scheduler)

    await executor.execute(
        [
            ToolCall(
                name="create_task",
                arguments={
                    "task_ref": "task_0",
                    "title": "drink water",
                    "category": "health",
                },
            ),
            ToolCall(
                name="schedule_reminder",
                arguments={
                    "task_ref": "task_0",
                    "resolved_time": _future_hhmm("Asia/Kathmandu"),
                },
            ),
        ],
        ToolExecutionContext(
            user=user,
            session_id="session-1",
            chat_id=123,
            timezone="Asia/Kathmandu",
        ),
    )

    assert len(store.tasks) == 1
    assert len(store.reminders) == 1
    assert len(scheduler.scheduled) == 1
