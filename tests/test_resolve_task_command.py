"""Shared Task/Reminder terminal-resolution contract tests."""

import httpx
import pytest
from fastapi import FastAPI

from src.api.tasks import router
from src.auth import get_authenticated_user_id
from src.bot.reminder_actions import ReminderActions
from src.commands.base import (
    CommandContext,
    IdempotencyConflictError,
    InvalidTransitionError,
    StaleVersionError,
)
from src.commands.tasks import ResolveTaskCommand
from src.memory.memory_store import InMemoryStore
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


def _reminders(store) -> list[dict]:
    return store.reminders if isinstance(store, FakeStore) else list(store._reminders.values())


def _outbox(store) -> dict[str, dict]:
    return store.scheduler_outbox if isinstance(store, FakeStore) else store._scheduler_outbox


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
@pytest.mark.parametrize("outcome", ["completed", "skipped", "cancelled"])
async def test_resolve_task_applies_each_terminal_outcome(store_factory, outcome):
    store = store_factory()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "Finish report")

    result = await ResolveTaskCommand(store).run(
        CommandContext(user["user_id"], "telegram", f"resolve-{outcome}"),
        task_id=task["task_id"],
        outcome=outcome,
        expected_version=1,
    )

    assert result["task"]["status"] == outcome
    assert result["task_version"] == 2
    assert result["transitioned"] is True
    assert bool(result["task"]["actual_completion"]) is (outcome == "completed")


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_sent_reminder_is_acknowledged_and_cancel_effect_is_durable(store_factory):
    store = store_factory()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "Finish report")
    reminder = await store.create_reminder(
        task["task_id"],
        user["user_id"],
        "2099-01-01T00:00:00",
    )
    await store.update_reminder(reminder["reminder_id"], {"status": "sent"}, user["user_id"])

    result = await ResolveTaskCommand(store).run(
        CommandContext(user["user_id"], "telegram", "resolve-from-reminder"),
        task_id=task["task_id"],
        outcome="completed",
        acted_reminder_id=reminder["reminder_id"],
    )

    assert _reminders(store)[0]["status"] == "acknowledged"
    assert result["effect_state"] == "queued"
    assert list(_outbox(store)) == [f"cancel:{reminder['reminder_id']}"]


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_resolution_replay_and_repeated_action_never_transition_twice(store_factory):
    store = store_factory()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "Finish report")
    await store.create_reminder(
        task["task_id"],
        user["user_id"],
        "2099-01-01T00:00:00",
    )
    command = ResolveTaskCommand(store)
    context = CommandContext(user["user_id"], "telegram", "resolve-replay")

    first = await command.run(context, task_id=task["task_id"], outcome="completed")
    replay = await command.run(context, task_id=task["task_id"], outcome="completed")
    repeated = await command.run(
        CommandContext(user["user_id"], "telegram", "resolve-repeated-button"),
        task_id=task["task_id"],
        outcome="completed",
    )

    assert replay == first
    assert repeated["transitioned"] is False
    assert repeated["task_version"] == 2
    assert len(_outbox(store)) == 1
    assert _reminders(store)[0]["status"] == "cancelled"

    with pytest.raises(IdempotencyConflictError):
        await command.run(context, task_id=task["task_id"], outcome="skipped")
    with pytest.raises(InvalidTransitionError):
        await command.run(
            CommandContext(user["user_id"], "telegram", "resolve-different-outcome"),
            task_id=task["task_id"],
            outcome="skipped",
        )


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_stale_and_wrong_owner_resolution_do_not_mutate(store_factory):
    store = store_factory()
    owner = await store.create_user(123)
    intruder = await store.create_user(456)
    task = await store.create_task(owner["user_id"], "Private report")
    reminder = await store.create_reminder(
        task["task_id"],
        owner["user_id"],
        "2099-01-01T00:00:00",
    )
    command = ResolveTaskCommand(store)

    with pytest.raises(StaleVersionError):
        await command.run(
            CommandContext(owner["user_id"], "dashboard", "resolve-stale"),
            task_id=task["task_id"],
            outcome="completed",
            expected_version=2,
        )
    with pytest.raises(ValueError, match="Task not found"):
        await command.run(
            CommandContext(intruder["user_id"], "dashboard", "resolve-intruder"),
            task_id=task["task_id"],
            outcome="completed",
            expected_version=1,
        )

    assert task["status"] == "pending"
    assert _reminders(store)[0]["status"] == "pending"
    assert _outbox(store) == {}
    assert reminder["reminder_id"]


async def test_dashboard_and_telegram_use_the_same_resolution_contract():
    store = FakeStore()
    user = await store.create_user(123)
    await store.update_user(user["user_id"], {"supabase_auth_id": "auth-user"})
    dashboard_task = await store.create_task(user["user_id"], "Dashboard report")
    dashboard_reminder = await store.create_reminder(
        dashboard_task["task_id"],
        user["user_id"],
        "2099-01-01T00:00:00",
    )
    telegram_task = await store.create_task(user["user_id"], "Telegram report")
    telegram_reminder = await store.create_reminder(
        telegram_task["task_id"],
        user["user_id"],
        "2099-01-01T00:00:00",
    )
    await store.update_reminder(
        telegram_reminder["reminder_id"],
        {"status": "sent"},
        user["user_id"],
    )

    app = FastAPI()
    app.state.store = store
    app.include_router(router)
    app.dependency_overrides[get_authenticated_user_id] = lambda: "auth-user"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        dashboard = await client.post(
            f"/api/tasks/{dashboard_task['task_id']}/resolve",
            headers={"Idempotency-Key": "dashboard-resolve"},
            json={"outcome": "skipped", "expected_version": 1},
        )
        stale = await client.post(
            f"/api/tasks/{telegram_task['task_id']}/resolve",
            headers={"Idempotency-Key": "dashboard-stale"},
            json={"outcome": "completed", "expected_version": 2},
        )

    actions = ReminderActions(FakeChannel(), store, FakeScheduler())
    await actions.handle_callback(123, 1, f"done:{telegram_reminder['reminder_id']}")

    assert dashboard.status_code == 202
    assert dashboard.json()["task"]["status"] == "skipped"
    assert stale.status_code == 409
    assert dashboard_reminder["status"] == "cancelled"
    assert telegram_task["status"] == "completed"
    assert telegram_reminder["status"] == "acknowledged"
    assert len(_outbox(store)) == 2
