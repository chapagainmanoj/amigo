"""Reminder scheduling and inline callback actions."""

import logging

from src.agent.agent import parse_time_expression
from src.channels.base import MessageChannel
from src.commands.base import CommandContext, InvalidTransitionError
from src.commands.later import ApplyLaterCommand
from src.memory.store import MemoryStore
from src.scheduler.reminders import ReminderScheduler
from src.tools.reminders import CancelRemindersTool, ScheduleReminderTool
from src.tools.tasks import UpdateTaskStatusTool

logger = logging.getLogger(__name__)


class ReminderActions:
    """Coordinates task reminder persistence, scheduling, and callbacks."""

    def __init__(
        self,
        channel: MessageChannel,
        store: MemoryStore,
        scheduler: ReminderScheduler,
    ):
        self.channel = channel
        self.store = store
        self.scheduler = scheduler
        self.cancel_reminders_tool = CancelRemindersTool(store, scheduler)
        self.schedule_reminder_tool = ScheduleReminderTool(store, scheduler)
        self.update_task_status_tool = UpdateTaskStatusTool(store)
        self.apply_later_command = ApplyLaterCommand(store)

    async def schedule_for_task(
        self, user: dict, task: dict, time_expr: str, chat_id: int
    ) -> None:
        """Resolve a time expression and schedule a reminder in UTC.

        Only unambiguous relative expressions may bypass explicit confirmation.
        """
        try:
            tz = user.get("timezone") or "UTC"
            resolved = parse_time_expression(time_expr, tz)
            if (
                resolved.clarification_required
                or resolved.confirmation_required
                or resolved.utc_instant is None
            ):
                logger.warning("Time expression requires clarification: %s", time_expr)
                return
            await self.schedule_reminder_tool.run_exact(
                context=CommandContext(
                    actor_user_id=user["user_id"],
                    surface="telegram",
                    idempotency_key=f"telegram:legacy-schedule:{task['task_id']}:{time_expr}",
                ),
                task=task,
                scheduled_at=resolved.utc_instant,
                timezone=tz,
            )
        except Exception:
            logger.exception("Failed to schedule reminder for task: %s", task["title"])

    async def cancel_for_task(self, task_id: str, user_id: str) -> None:
        """Acknowledge all pending reminders for a task and cancel scheduler jobs."""
        await self.cancel_reminders_tool.run(task_id=task_id, user_id=user_id)

    async def handle_callback(self, chat_id: int, message_id: int, data: str) -> None:
        """Handle Done/Skip/Later reminder button callbacks."""
        parts = data.split(":", 1)
        if len(parts) != 2:
            return

        action, reminder_id = parts

        user = await self.store.get_user_by_chat_id(chat_id)
        if not user:
            return

        reminder = await self.store.get_reminder_with_task(reminder_id, user["user_id"])
        if not reminder:
            logger.warning(
                "Callback ownership mismatch: chat %s, reminder %s",
                chat_id,
                reminder_id,
            )
            return

        await self.channel.edit_message_buttons(chat_id, message_id, buttons=None)

        if action == "done":
            if not await self._resolve_from_callback(reminder, reminder_id, "done", "completed"):
                await self.channel.send_message(chat_id, "This task was already resolved.")
                return
            await self.channel.send_message(
                chat_id, f"✅ Nice — \"{reminder['tasks']['title']}\" done!"
            )

        elif action == "skip":
            if not await self._resolve_from_callback(reminder, reminder_id, "skip", "skipped"):
                await self.channel.send_message(chat_id, "This task was already resolved.")
                return
            await self.channel.send_message(chat_id, "Skipped ⏭️")

        elif action == "later":
            await self._handle_later(chat_id, reminder_id, reminder)

    async def _resolve_from_callback(
        self,
        reminder: dict,
        reminder_id: str,
        action: str,
        outcome: str,
    ) -> bool:
        try:
            await self.update_task_status_tool.run(
                context=CommandContext(
                    actor_user_id=reminder["user_id"],
                    surface="telegram",
                    idempotency_key=f"telegram:reminder:{reminder_id}:{action}",
                ),
                task_id=reminder["task_id"],
                status=outcome,
                acted_reminder_id=reminder_id,
            )
        except InvalidTransitionError:
            return False
        return True

    async def _handle_later(self, chat_id: int, reminder_id: str, reminder: dict) -> None:
        """Apply the canonical Later policy without rewinding the current Reminder."""
        try:
            result = await self.apply_later_command.run(
                CommandContext(
                    actor_user_id=reminder["user_id"],
                    surface="telegram",
                    idempotency_key=f"telegram:reminder:{reminder_id}:later",
                ),
                reminder_id=reminder_id,
            )
        except ValueError:
            await self.channel.send_message(chat_id, "This reminder was already handled.")
            return

        local_time = result["intended_local_time"][:5]
        adjustment = " (moved past quiet hours)" if result["quiet_hours_adjusted"] else ""
        await self.channel.send_message(
            chat_id,
            (
                f"⏰ Next reminder: {result['intended_local_date']} at {local_time} "
                f"{result['intended_timezone']}{adjustment}."
            ),
        )
