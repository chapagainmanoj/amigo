"""Task tools used by the app layer."""

from src.memory.store import MemoryStore
from src.tools.reminders import CancelRemindersTool


class CreateTaskTool:
    """Create a task through the store layer."""

    name = "create_task"

    def __init__(self, store: MemoryStore):
        self.store = store

    async def run(
        self,
        *,
        user_id: str,
        title: str,
        category: str = "other",
        session_id: str | None = None,
        suggested_time: str | None = None,
        timezone: str = "UTC",
    ) -> dict:
        task = await self.store.create_task(
            user_id=user_id,
            title=title,
            category=category,
            session_id=session_id,
            suggested_time=suggested_time,
            timezone=timezone,
        )
        return {"task": task}


class UpdateTaskStatusTool:
    """Update task status and cancel pending reminders for that task."""

    name = "update_task_status"

    def __init__(self, store: MemoryStore, cancel_reminders: CancelRemindersTool):
        self.store = store
        self.cancel_reminders = cancel_reminders

    async def run(self, *, task_id: str, status: str, user_id: str) -> dict:
        task = await self.store.update_task_status(task_id, status)
        cancelled = await self.cancel_reminders.run(task_id=task_id, user_id=user_id)
        return {"task": task, "cancelled_reminders": cancelled["reminder_ids"]}
