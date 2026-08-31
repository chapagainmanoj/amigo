"""Task tools used by the app layer."""

from datetime import date

from src.commands.base import CommandContext
from src.commands.tasks import CreateTaskCommand, CreateTaskInput, ResolveTaskCommand
from src.memory.store import MemoryStore


class CreateTaskTool:
    """Create a task through the store layer."""

    name = "create_task"

    def __init__(self, store: MemoryStore):
        self.command = CreateTaskCommand(store)

    async def run(
        self,
        *,
        context: CommandContext,
        title: str,
        category: str = "other",
        session_id: str | None = None,
        planning_day: date | None = None,
    ) -> dict:
        return await self.command.run(
            context,
            CreateTaskInput(
                title=title,
                category=category,
                planning_day=planning_day,
                source_session_id=session_id,
            ),
        )


class UpdateTaskStatusTool:
    """Resolve a Task and its active Reminders through the shared command."""

    name = "update_task_status"

    def __init__(self, store: MemoryStore):
        self.command = ResolveTaskCommand(store)

    async def run(
        self,
        *,
        context: CommandContext,
        task_id: str,
        status: str,
        expected_version: int | None = None,
        acted_reminder_id: str | None = None,
    ) -> dict:
        return await self.command.run(
            context,
            task_id=task_id,
            outcome=status,
            expected_version=expected_version,
            acted_reminder_id=acted_reminder_id,
        )
