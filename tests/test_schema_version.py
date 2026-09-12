"""Exact database schema gate and startup-order regressions."""

from types import SimpleNamespace

import pytest

from src.memory.memory_store import InMemoryStore
from src.memory.store import MemoryStore
from src.schema import (
    EXPECTED_SCHEMA_VERSION,
    SchemaVersionMismatchError,
    require_schema_version,
)
from src.startup import initialize_runtime
from tests.fakes import FakeStore


class _SchemaDatabase:
    def __init__(self, version):
        self.version = version
        self.calls = []

    def rpc(self, name):
        self.calls.append(name)

        async def execute():
            return SimpleNamespace(data=self.version)

        return SimpleNamespace(execute=execute)


def test_schema_version_requires_an_exact_integer():
    assert require_schema_version(EXPECTED_SCHEMA_VERSION) == EXPECTED_SCHEMA_VERSION
    for invalid in (EXPECTED_SCHEMA_VERSION - 1, EXPECTED_SCHEMA_VERSION + 1, "14", True, None):
        with pytest.raises(SchemaVersionMismatchError):
            require_schema_version(invalid)


async def test_memory_store_reads_service_only_schema_marker():
    database = _SchemaDatabase(EXPECTED_SCHEMA_VERSION)
    store = MemoryStore.__new__(MemoryStore)
    store.db = database

    assert await store.verify_schema_version(EXPECTED_SCHEMA_VERSION) == EXPECTED_SCHEMA_VERSION
    assert database.calls == ["get_app_schema_version"]


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_local_stores_mirror_schema_mismatch_behavior(store_factory):
    store = store_factory()
    assert await store.verify_schema_version(EXPECTED_SCHEMA_VERSION) == EXPECTED_SCHEMA_VERSION
    with pytest.raises(SchemaVersionMismatchError):
        await store.verify_schema_version(EXPECTED_SCHEMA_VERSION + 1)


class _StartupStore:
    def __init__(self, events, *, fail_schema=False):
        self.events = events
        self.fail_schema = fail_schema

    async def connect(self):
        self.events.append("connect")

    async def verify_schema_version(self, expected):
        self.events.append(f"schema:{expected}")
        if self.fail_schema:
            raise SchemaVersionMismatchError("wrong schema")


class _StartupScheduler:
    def __init__(self, events):
        self.events = events

    def start(self):
        self.events.append("scheduler:start")

    def start_outbox_worker(self, _drain):
        self.events.append("scheduler:outbox")

    def start_reconciliation(self, _reconcile):
        self.events.append("scheduler:reconcile")

    async def reconcile(self):
        return None

    async def reload_pending(self):
        self.events.append("scheduler:reload")


class _StartupOutbox:
    def __init__(self, events):
        self.events = events

    async def drain_once(self):
        self.events.append("outbox:drain")


async def test_schema_mismatch_stops_before_scheduler_or_outbox_side_effects():
    events = []
    with pytest.raises(SchemaVersionMismatchError):
        await initialize_runtime(
            _StartupStore(events, fail_schema=True),
            _StartupScheduler(events),
            _StartupOutbox(events),
        )
    assert events == ["connect", f"schema:{EXPECTED_SCHEMA_VERSION}"]


async def test_verified_schema_precedes_scheduler_recovery():
    events = []
    await initialize_runtime(
        _StartupStore(events),
        _StartupScheduler(events),
        _StartupOutbox(events),
    )
    assert events == [
        "connect",
        f"schema:{EXPECTED_SCHEMA_VERSION}",
        "scheduler:start",
        "scheduler:outbox",
        "scheduler:reconcile",
        "outbox:drain",
        "scheduler:reload",
    ]
