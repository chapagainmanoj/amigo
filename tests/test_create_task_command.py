"""Shared Create Task command and dashboard adapter coverage."""

from datetime import date

import httpx
import pytest
from fastapi import FastAPI

from src.api.tasks import router
from src.auth import get_authenticated_user_id
from src.commands.base import CommandContext, IdempotencyConflictError
from src.commands.tasks import CreateTaskCommand, CreateTaskInput
from src.memory.memory_store import InMemoryStore
from src.utils import today_in_tz
from tests.fakes import FakeStore


def _task_count(store) -> int:
    if isinstance(store, FakeStore):
        return len(store.tasks)
    return len(store._tasks)


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_inbox_task_replay_returns_stored_result(store_factory):
    store = store_factory()
    user = await store.create_user(123)
    command = CreateTaskCommand(store)
    context = CommandContext(
        actor_user_id=user["user_id"],
        surface="telegram",
        idempotency_key="telegram:update-1:create-task-1",
    )
    task_input = CreateTaskInput(title="  Call Mom  ", category="social")

    first = await command.run(context, task_input)
    replay = await command.run(context, task_input)

    assert replay == first
    assert _task_count(store) == 1
    assert first["task"]["title"] == "Call Mom"
    assert first["task"]["status"] == "pending"
    assert first["task"]["due_date"] is None
    assert first["task"]["created_date"] is not None
    assert await store.get_today_tasks(user["user_id"], "UTC") == []
    assert await store.get_inbox_tasks(user["user_id"]) == [first["task"]]


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_idempotency_key_reuse_with_different_input_does_not_mutate(store_factory):
    store = store_factory()
    user = await store.create_user(123)
    command = CreateTaskCommand(store)
    context = CommandContext(user["user_id"], "dashboard", "dashboard-request-1")

    await command.run(context, CreateTaskInput(title="First"))
    with pytest.raises(IdempotencyConflictError):
        await command.run(context, CreateTaskInput(title="Different"))

    assert _task_count(store) == 1


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_planned_task_uses_due_date_for_today_population(store_factory):
    store = store_factory()
    user = await store.create_user(123)
    planning_day = today_in_tz("UTC")

    result = await CreateTaskCommand(store).run(
        CommandContext(user["user_id"], "dashboard", "dashboard-request-2"),
        CreateTaskInput(title="Planned", planning_day=planning_day),
    )

    assert result["task"]["due_date"] == planning_day.isoformat()
    assert await store.get_today_tasks(user["user_id"], "UTC") == [result["task"]]
    assert await store.get_inbox_tasks(user["user_id"]) == []


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_same_task_title_is_allowed_on_different_planning_days(store_factory):
    store = store_factory()
    user = await store.create_user(123)
    command = CreateTaskCommand(store)

    first = await command.run(
        CommandContext(user["user_id"], "telegram", "telegram:501:create-task:1"),
        CreateTaskInput(title="Walk", planning_day=date(2026, 8, 31)),
    )
    second = await command.run(
        CommandContext(user["user_id"], "telegram", "telegram:502:create-task:1"),
        CreateTaskInput(title="Walk", planning_day=date(2026, 9, 1)),
    )

    assert first["task"]["task_id"] != second["task"]["task_id"]
    assert first["task"]["due_date"] == "2026-08-31"
    assert second["task"]["due_date"] == "2026-09-01"


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_cross_tenant_source_session_is_rejected(store_factory):
    store = store_factory()
    owner = await store.create_user(123)
    intruder = await store.create_user(456)
    session = await store.create_session(owner["user_id"])

    with pytest.raises(ValueError, match="Session not found"):
        await CreateTaskCommand(store).run(
            CommandContext(intruder["user_id"], "telegram", "telegram-request-2"),
            CreateTaskInput(title="Cross-linked", source_session_id=session["session_id"]),
        )

    assert _task_count(store) == 0


async def test_dashboard_adapter_resolves_actor_and_replays():
    store = FakeStore()
    user = await store.create_user(123)
    await store.update_user(user["user_id"], {"supabase_auth_id": "auth-user"})
    app = FastAPI()
    app.state.store = store
    app.include_router(router)
    app.dependency_overrides[get_authenticated_user_id] = lambda: "auth-user"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/api/tasks",
            headers={"Idempotency-Key": "dashboard-request-3"},
            json={"title": "Inbox from dashboard", "category": "work"},
        )
        replay = await client.post(
            "/api/tasks",
            headers={"Idempotency-Key": "dashboard-request-3"},
            json={"title": "Inbox from dashboard", "category": "work"},
        )
        conflict = await client.post(
            "/api/tasks",
            headers={"Idempotency-Key": "dashboard-request-3"},
            json={"title": "Different"},
        )
        supplied_identity = await client.post(
            "/api/tasks",
            headers={"Idempotency-Key": "dashboard-request-4"},
            json={"title": "Attempt", "user_id": "attacker-selected"},
        )

    assert first.status_code == 200
    assert replay.json() == first.json()
    assert conflict.status_code == 409
    assert supplied_identity.status_code == 422
    assert _task_count(store) == 1
    assert first.json()["task"]["user_id"] == user["user_id"]


def test_create_task_input_has_no_participant_identity():
    with pytest.raises(TypeError):
        CreateTaskInput(title="Attempt", user_id="attacker-selected")


def test_planning_day_is_a_typed_date():
    task_input = CreateTaskInput(title="Plan", planning_day=date(2026, 8, 30))
    assert task_input.planning_day == date(2026, 8, 30)
