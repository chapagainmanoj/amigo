"""Regressions for native-async Supabase access and event-loop progress."""

import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace

from src import auth as auth_module
from src.db import supabase as supabase_module
from src.memory.store import MemoryStore
from src.observability import monitor_event_loop_delay

ROOT = Path(__file__).resolve().parents[1]


def _is_awaited(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.Await):
            return True
        if isinstance(current, (ast.AsyncFunctionDef, ast.FunctionDef)):
            return False
    return False


def test_supabase_network_calls_are_statically_awaited():
    checked_calls = 0
    for relative_path, method_names in (
        ("src/memory/store.py", {"execute"}),
        ("src/auth.py", {"get_user"}),
    ):
        tree = ast.parse((ROOT / relative_path).read_text())
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in method_names:
                continue
            checked_calls += 1
            assert _is_awaited(node, parents), (
                f"{relative_path}:{node.lineno} executes Supabase I/O without await"
            )
    assert checked_calls >= 48


class _ConcurrentQuery:
    def __init__(self, database):
        self.database = database

    def select(self, _columns):
        return self

    def eq(self, _column, _value):
        return self

    def maybe_single(self):
        return self

    async def execute(self):
        self.database.started += 1
        if self.database.started == self.database.expected:
            self.database.all_started.set()
        await self.database.release.wait()
        return SimpleNamespace(data=None)


class _ConcurrentDatabase:
    def __init__(self, expected: int):
        self.expected = expected
        self.started = 0
        self.all_started = asyncio.Event()
        self.release = asyncio.Event()

    def table(self, table_name):
        assert table_name == "user_profiles"
        return _ConcurrentQuery(self)


async def test_store_database_calls_yield_and_overlap_on_the_event_loop():
    operation_count = 20
    database = _ConcurrentDatabase(operation_count)
    store = MemoryStore.__new__(MemoryStore)
    store.db = database
    loop_progress = 0
    stop_ticker = asyncio.Event()

    async def ticker():
        nonlocal loop_progress
        while not stop_ticker.is_set():
            loop_progress += 1
            await asyncio.sleep(0)

    ticker_task = asyncio.create_task(ticker())
    calls = [
        asyncio.create_task(store.get_user_by_chat_id(chat_id))
        for chat_id in range(operation_count)
    ]
    await asyncio.wait_for(database.all_started.wait(), timeout=0.25)
    assert loop_progress > 0
    assert database.started == operation_count

    database.release.set()
    await asyncio.gather(*calls)
    stop_ticker.set()
    await ticker_task


async def test_async_supabase_singleton_initializes_once_under_concurrency(monkeypatch):
    created_client = object()
    calls = 0

    async def create_client(_url, _key):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return created_client

    monkeypatch.setattr(supabase_module, "_client", None)
    monkeypatch.setattr(supabase_module, "_client_lock", asyncio.Lock())
    monkeypatch.setattr(supabase_module, "acreate_client", create_client)

    clients = await asyncio.gather(*(supabase_module.get_supabase() for _ in range(20)))

    assert calls == 1
    assert all(client is created_client for client in clients)


async def test_memory_store_connects_to_the_shared_async_client(monkeypatch):
    client = object()

    async def get_client():
        return client

    monkeypatch.setattr(supabase_module, "get_supabase", get_client)
    store = MemoryStore()

    await store.connect()

    assert store.db is client


async def test_authentication_awaits_native_async_user_verification(monkeypatch):
    received_tokens = []

    class Auth:
        async def get_user(self, token):
            received_tokens.append(token)
            await asyncio.sleep(0)
            return SimpleNamespace(user=SimpleNamespace(id="auth-user"))

    async def get_client():
        return SimpleNamespace(auth=Auth())

    monkeypatch.setattr(auth_module, "get_supabase", get_client)

    user_id = await auth_module.get_authenticated_user_id("Bearer signed-token")

    assert user_id == "auth-user"
    assert received_tokens == ["signed-token"]


async def test_event_loop_delay_and_store_latency_are_content_free(caplog):
    caplog.set_level(logging.INFO)
    stop_event = asyncio.Event()

    await monitor_event_loop_delay(
        stop_event,
        interval_seconds=0.001,
        sample_limit=2,
    )

    database = _ConcurrentDatabase(expected=1)
    database.release.set()
    store = MemoryStore.__new__(MemoryStore)
    store.db = database
    await store.get_user_by_chat_id(123)

    assert "event_loop_delay_ms=" in caplog.text
    assert "database_operation=get_user_by_chat_id" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "chat_id=" not in caplog.text
    assert "user_id=" not in caplog.text
