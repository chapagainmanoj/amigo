"""Migration 016's confirmed result cannot be recovered through its seven Store APIs.

This pins the known gap for Phase 4: a simulated application crash preserves committed Store
state but drops the callback's local result. It does not claim process durability for local Stores.
"""

import pytest

from src.memory.memory_store import InMemoryStore
from tests.fakes import FakeStore


class InjectedCrashError(RuntimeError):
    """Application stopped after confirmation, before target execution."""


@pytest.mark.parametrize("store_type", [InMemoryStore, FakeStore])
async def test_016_confirmation_crash_consumes_request_before_target_execution(store_type):
    store = store_type()
    user = await store.create_user(91016099)
    user_id = user["user_id"]
    session = await store.create_session(user_id)
    session_id = session["session_id"]
    assert (await store.grant_mode(user_id, "coach", "test-operator", "fictional trial"))[
        "status"
    ] == "granted"
    assert (await store.set_active_mode(user_id, session_id, "coach"))["status"] == "set"
    pending = await store.create_handoff(
        user_id, session_id, "coach", "daily", "Add a fictional reading Task"
    )
    handoff_id = pending["handoff"]["handoff_id"]
    target_runs = []

    async def confirm_then_execute():
        result = await store.resolve_handoff(user_id, session_id, handoff_id, True)
        assert result["status"] == "confirmed"
        # Inject exactly at the committed-confirmation / target-execution boundary.
        raise InjectedCrashError
        target_runs.append(result["handoff"]["carried_request"])  # pragma: no cover

    with pytest.raises(InjectedCrashError):
        await confirm_then_execute()

    # Committed confirmation switched the Session; no target Turn ran. Re-delivery cannot obtain
    # the carried request from resolve_handoff, even though application execution never began.
    assert await store.get_active_mode(user_id, session_id) is None
    assert await store.resolve_handoff(user_id, session_id, handoff_id, True) == {
        "status": "unavailable"
    }
    assert target_runs == []
    assert await store.get_today_tasks(user_id, "UTC") == []
