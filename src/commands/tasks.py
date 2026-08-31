"""Canonical Task application commands."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal

from src.commands.base import CommandContext


@dataclass(frozen=True)
class CreateTaskInput:
    """User-controlled Create Task fields; participant identity is intentionally absent."""

    title: str
    category: str = "other"
    planning_day: date | None = None
    source_session_id: str | None = None


class CreateTaskCommand:
    """Create one canonical Task through an authenticated, idempotent Store operation."""

    def __init__(self, store):
        self.store = store

    async def run(self, context: CommandContext, task_input: CreateTaskInput) -> dict:
        title = task_input.title.strip()
        if not title:
            raise ValueError("Task title cannot be empty")
        if task_input.category not in {"health", "work", "personal", "social", "other"}:
            raise ValueError("Invalid Task category")
        if not context.idempotency_key.strip() or len(context.idempotency_key) > 200:
            raise ValueError("Invalid idempotency key")

        normalized_input = asdict(task_input)
        normalized_input["title"] = title
        if task_input.planning_day:
            normalized_input["planning_day"] = task_input.planning_day.isoformat()
        payload = {
            "command": "create_task",
            "surface": context.surface,
            "input": normalized_input,
        }
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        return await self.store.create_task_command(
            user_id=context.actor_user_id,
            idempotency_key=context.idempotency_key,
            payload_hash=payload_hash,
            title=title,
            category=task_input.category,
            due_date=(task_input.planning_day.isoformat() if task_input.planning_day else None),
            session_id=task_input.source_session_id,
        )


TaskOutcome = Literal["completed", "skipped", "cancelled"]


class ResolveTaskCommand:
    """Resolve one owned Task and its active Reminders in one idempotent transaction."""

    def __init__(self, store):
        self.store = store

    async def run(
        self,
        context: CommandContext,
        *,
        task_id: str,
        outcome: TaskOutcome,
        expected_version: int | None = None,
        acted_reminder_id: str | None = None,
    ) -> dict:
        if outcome not in {"completed", "skipped", "cancelled"}:
            raise ValueError("Invalid Task outcome")
        if expected_version is not None and expected_version < 1:
            raise ValueError("Invalid Task version")
        if not context.idempotency_key.strip() or len(context.idempotency_key) > 200:
            raise ValueError("Invalid idempotency key")

        payload = {
            "command": "resolve_task",
            "surface": context.surface,
            "task_id": task_id,
            "outcome": outcome,
            "expected_version": expected_version,
            "acted_reminder_id": acted_reminder_id,
        }
        payload_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return await self.store.resolve_task_command(
            user_id=context.actor_user_id,
            idempotency_key=context.idempotency_key,
            payload_hash=payload_hash,
            task_id=task_id,
            outcome=outcome,
            expected_version=expected_version,
            acted_reminder_id=acted_reminder_id,
        )
