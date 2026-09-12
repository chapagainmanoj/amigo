"""Canonical planning-day movement and agent adapter tests."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from src.agent.agent import move_task_planning_day
from src.commands.base import CommandContext, IdempotencyConflictError, StaleVersionError
from src.commands.tasks import MoveTaskPlanningDayCommand
from src.memory.memory_store import InMemoryStore
from tests.fakes import FakeStore
from tests.test_agent_lifecycle_tools import _deps


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_move_planning_day_is_owned_versioned_and_replayable(store_factory):
    store = store_factory()
    owner = await store.create_user(123)
    intruder = await store.create_user(456)
    task = await store.create_task(owner["user_id"], "Review budget")
    command = MoveTaskPlanningDayCommand(store)
    context = CommandContext(owner["user_id"], "telegram", "move-task-1")

    first = await command.run(
        context,
        task_id=task["task_id"],
        planning_day=date(2026, 9, 2),
        expected_version=1,
    )
    replay = await command.run(
        context,
        task_id=task["task_id"],
        planning_day=date(2026, 9, 2),
        expected_version=1,
    )

    assert replay == first
    assert first["task"]["due_date"] == "2026-09-02"
    assert first["task"]["version"] == 2

    with pytest.raises(IdempotencyConflictError):
        await command.run(
            context,
            task_id=task["task_id"],
            planning_day=date(2026, 9, 3),
            expected_version=1,
        )
    with pytest.raises(ValueError, match="Task not found"):
        await command.run(
            CommandContext(intruder["user_id"], "telegram", "cross-tenant-move"),
            task_id=task["task_id"],
            planning_day=date(2026, 9, 3),
            expected_version=2,
        )
    with pytest.raises(StaleVersionError):
        await command.run(
            CommandContext(owner["user_id"], "telegram", "stale-move"),
            task_id=task["task_id"],
            planning_day=date(2026, 9, 3),
            expected_version=1,
        )


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_move_planning_day_rejects_nonexistent_actor_consistently(store_factory):
    store = store_factory()
    owner = await store.create_user(123)
    task = await store.create_task(owner["user_id"], "Review budget")

    with pytest.raises(ValueError, match="User not found"):
        await MoveTaskPlanningDayCommand(store).run(
            CommandContext(
                "00000000-0000-0000-0000-000000000000",
                "telegram",
                "unknown-actor-move",
            ),
            task_id=task["task_id"],
            planning_day=date(2026, 9, 2),
            expected_version=1,
        )


async def test_agent_move_planning_day_uses_fixed_clock_and_owned_task():
    store, deps = await _deps()
    deps.clock.value = datetime(2026, 9, 1, 4, 15)
    task = await store.create_task(deps.user["user_id"], "Review budget")

    result = await move_task_planning_day(
        SimpleNamespace(deps=deps),
        task["task_id"],
        date(2026, 9, 2),
        1,
    )

    assert result == "Moved 'Review budget' to 2026-09-02."
    assert store._tasks[task["task_id"]]["due_date"] == "2026-09-02"

    replay = await move_task_planning_day(
        SimpleNamespace(deps=deps),
        task["task_id"],
        date(2026, 9, 2),
        1,
    )

    assert replay == result
    assert store._tasks[task["task_id"]]["version"] == 2
