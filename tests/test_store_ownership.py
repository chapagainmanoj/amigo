"""Tenant-ownership regression tests for Supabase-backed store mutations."""

import pytest

from src.memory.memory_store import InMemoryStore
from src.memory.store import MemoryStore
from src.utils import utc_now
from tests.fakes import FakeStore


class _Result:
    def __init__(self, data):
        self.data = data


class _TaskQuery:
    def __init__(self):
        self.filters = []

    def update(self, _updates):
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        return _Result([])


class _Database:
    def __init__(self):
        self.query = _TaskQuery()

    def table(self, table_name):
        assert table_name == "tasks"
        return self.query


async def test_supabase_task_status_update_filters_by_user_id():
    store = MemoryStore.__new__(MemoryStore)
    store.db = _Database()

    with pytest.raises(ValueError, match="Task not found"):
        await store.update_task_status("task-1", "completed", "intruder-1")

    assert ("task_id", "task-1") in store.db.query.filters
    assert ("user_id", "intruder-1") in store.db.query.filters


class _ReminderQuery(_TaskQuery):
    def select(self, _columns):
        return self

    def maybe_single(self):
        return self


class _ReminderDatabase:
    def __init__(self):
        self.query = _ReminderQuery()

    def table(self, table_name):
        assert table_name == "reminders"
        return self.query


async def test_supabase_reminder_update_filters_by_user_id():
    store = MemoryStore.__new__(MemoryStore)
    store.db = _ReminderDatabase()

    with pytest.raises(ValueError, match="Reminder not found"):
        await store.update_reminder("reminder-1", {"status": "sent"}, "intruder-1")

    assert ("reminder_id", "reminder-1") in store.db.query.filters
    assert ("user_id", "intruder-1") in store.db.query.filters


async def test_supabase_reminder_claim_filters_by_user_id():
    store = MemoryStore.__new__(MemoryStore)
    store.db = _ReminderDatabase()

    assert await store.claim_reminder_for_send("reminder-1", "intruder-1") is None
    assert ("reminder_id", "reminder-1") in store.db.query.filters
    assert ("user_id", "intruder-1") in store.db.query.filters


async def test_supabase_reminder_read_filters_by_user_id():
    store = MemoryStore.__new__(MemoryStore)
    store.db = _ReminderDatabase()

    assert await store.get_reminder_with_task("reminder-1", "intruder-1") is None
    assert ("reminder_id", "reminder-1") in store.db.query.filters
    assert ("user_id", "intruder-1") in store.db.query.filters


class _TaskOwnershipDatabase:
    def __init__(self):
        self.query = _ReminderQuery()

    def table(self, table_name):
        assert table_name == "tasks"
        return self.query


async def test_supabase_reminder_creation_verifies_task_owner():
    store = MemoryStore.__new__(MemoryStore)
    store.db = _TaskOwnershipDatabase()

    with pytest.raises(ValueError, match="Task not found"):
        await store.create_reminder("task-1", "intruder-1", utc_now().isoformat())

    assert ("task_id", "task-1") in store.db.query.filters
    assert ("user_id", "intruder-1") in store.db.query.filters


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_cross_user_reminder_update_matches_missing_resource(store_factory):
    store = store_factory()
    owner = await store.create_user(1001)
    intruder = await store.create_user(1002)
    task = await store.create_task(owner["user_id"], "Owner task")
    reminder = await store.create_reminder(
        task["task_id"], owner["user_id"], utc_now().isoformat()
    )

    with pytest.raises(ValueError, match="Reminder not found") as cross_user:
        await store.update_reminder(
            reminder["reminder_id"], {"status": "sent"}, intruder["user_id"]
        )
    with pytest.raises(ValueError, match="Reminder not found") as missing:
        await store.update_reminder(
            "missing-reminder", {"status": "sent"}, intruder["user_id"]
        )

    assert str(cross_user.value) == str(missing.value)
    assert reminder["status"] == "pending"


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_cross_user_task_cannot_receive_reminder(store_factory):
    store = store_factory()
    owner = await store.create_user(2001)
    intruder = await store.create_user(2002)
    task = await store.create_task(owner["user_id"], "Owner task")

    with pytest.raises(ValueError, match="Task not found"):
        await store.create_reminder(
            task["task_id"], intruder["user_id"], utc_now().isoformat()
        )


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_cross_user_reminder_read_and_claim_are_invisible(store_factory):
    store = store_factory()
    owner = await store.create_user(3001)
    intruder = await store.create_user(3002)
    task = await store.create_task(owner["user_id"], "Owner task")
    reminder = await store.create_reminder(
        task["task_id"], owner["user_id"], utc_now().isoformat()
    )

    assert (
        await store.get_reminder_with_task(reminder["reminder_id"], intruder["user_id"])
        is None
    )
    assert (
        await store.claim_reminder_for_send(reminder["reminder_id"], intruder["user_id"])
        is None
    )
    assert reminder["status"] == "pending"


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_reminder_update_cannot_rewrite_ownership(store_factory):
    store = store_factory()
    owner = await store.create_user(4001)
    task = await store.create_task(owner["user_id"], "Owner task")
    reminder = await store.create_reminder(
        task["task_id"], owner["user_id"], utc_now().isoformat()
    )

    with pytest.raises(ValueError, match="Invalid reminder update"):
        await store.update_reminder(
            reminder["reminder_id"], {"user_id": "intruder"}, owner["user_id"]
        )

    assert reminder["user_id"] == owner["user_id"]
