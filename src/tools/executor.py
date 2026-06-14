"""Tool executor for agent-requested side effects."""

from dataclasses import dataclass, field
from typing import Any

from src.agent.models import ToolCall
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler
from src.tools.reminders import CancelRemindersTool, ScheduleReminderTool
from src.tools.tasks import CreateTaskTool, UpdateTaskStatusTool


@dataclass
class ToolExecutionContext:
    """Request context injected into tool calls by the application layer."""

    user: dict
    session_id: str
    chat_id: int
    timezone: str
    task_refs: dict[str, dict] = field(default_factory=dict)


class ToolExecutor:
    """Map agent tool calls to concrete Python services."""

    def __init__(self, store: MemoryStore, scheduler: ReminderScheduler):
        self.cancel_reminders = CancelRemindersTool(store, scheduler)
        self.tools = {
            CreateTaskTool.name: CreateTaskTool(store),
            ScheduleReminderTool.name: ScheduleReminderTool(store, scheduler),
            UpdateTaskStatusTool.name: UpdateTaskStatusTool(store, self.cancel_reminders),
            CancelRemindersTool.name: self.cancel_reminders,
        }

    async def execute(
        self, tool_calls: list[ToolCall], context: ToolExecutionContext
    ) -> list[dict[str, Any]]:
        """Execute tool calls sequentially so later calls can use earlier results."""
        results: list[dict[str, Any]] = []
        for call in tool_calls:
            tool = self.tools.get(call.name)
            if not tool:
                raise ValueError(f"Unknown tool call: {call.name}")

            args = dict(call.arguments)
            task_ref = args.pop("task_ref", None)

            if call.name == CreateTaskTool.name:
                result = await tool.run(
                    user_id=context.user["user_id"],
                    session_id=context.session_id,
                    timezone=context.timezone,
                    **args,
                )
                if task_ref:
                    context.task_refs[task_ref] = result["task"]

            elif call.name == ScheduleReminderTool.name:
                if not task_ref or task_ref not in context.task_refs:
                    raise ValueError("schedule_reminder requires a known task_ref")
                args.pop("original_time", None)
                result = await tool.run(
                    user_id=context.user["user_id"],
                    task=context.task_refs[task_ref],
                    timezone=context.timezone,
                    chat_id=context.chat_id,
                    **args,
                )

            elif call.name in (UpdateTaskStatusTool.name, CancelRemindersTool.name):
                result = await tool.run(user_id=context.user["user_id"], **args)

            results.append({"tool": call.name, "result": result})

        return results
