"""Unavailable confirmed handoffs leave the recovery queue; failures are fenced terminal writes."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from src.memory.store import MemoryStore
from tests.test_mode_conversation_store import confirmed
from tests.test_mode_conversation_store import store as store  # noqa: F401 - shared Store fixture


async def test_unavailable_claims_drain_first_page_and_leave_the_next_handoff_recoverable(store):
    api, user, _, _ = store
    handoffs = [await confirmed(api, user) for _ in range(26)]
    wrong = await api.create_session(user, mode_id="coach")
    first = await api.list_pending_handoff_executions()
    assert len(first) == 25
    for row in first:
        result = await api.claim_handoff_execution(
            user, row["handoff_id"], "recovery", execution_session_id=wrong["session_id"]
        )
        assert result["status"] == "unavailable"
    remaining = await api.list_pending_handoff_executions()
    assert [row["handoff_id"] for row in remaining] == [handoffs[-1][0]]
    assert (
        await api.claim_handoff_execution(
            user, handoffs[-1][0], "recovery", execution_session_id=handoffs[-1][1]
        )
    )["status"] == "claimed"


async def test_terminal_failure_checks_owner_current_lease_and_single_use(store):
    api, user, other, clock = store
    handoff, target = await confirmed(api, user)
    first = await api.claim_handoff_execution(user, handoff, "one", execution_session_id=target)
    old_token = first["handoff"]["execution_claim_token"]
    clock["now"] += timedelta(minutes=6)
    assert not await api.fail_handoff_execution(user, handoff, old_token, "execution_failed")
    second = await api.claim_handoff_execution(user, handoff, "two")
    token = second["handoff"]["execution_claim_token"]
    assert not await api.fail_handoff_execution(other, handoff, token, "execution_failed")
    assert not await api.fail_handoff_execution(user, handoff, old_token, "execution_failed")
    assert not await api.fail_handoff_execution(user, handoff, token, "private exception text")
    assert await api.fail_handoff_execution(user, handoff, token, "execution_failed")
    assert not await api.fail_handoff_execution(user, handoff, token, "execution_failed")
    assert not await api.complete_handoff_execution(user, handoff, token)
    assert not await api.save_handoff_execution_plan(user, handoff, token, [{"late": True}])
    assert await api.claim_handoff_execution(user, handoff, "three") == {"status": "failed"}
    assert not await api.list_pending_handoff_executions()


async def test_foreign_claim_does_not_terminalize_the_owners_handoff(store):
    api, user, other, _ = store
    handoff, target = await confirmed(api, user)
    assert await api.claim_handoff_execution(
        other, handoff, "foreign", execution_session_id=target
    ) == {"status": "unavailable"}
    assert (await api.claim_handoff_execution(user, handoff, "owner", execution_session_id=target))[
        "status"
    ] == "claimed"


async def test_terminal_failure_rpc_contract():
    store = MemoryStore()
    query = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(data=True)))
    store.db = SimpleNamespace(rpc=Mock(return_value=query))
    assert await store.fail_handoff_execution("owner", "handoff", "token", "execution_failed")
    store.db.rpc.assert_called_once_with(
        "fail_handoff_execution",
        {
            "p_user_id": "owner",
            "p_handoff_id": "handoff",
            "p_claim_token": "token",
            "p_reason": "execution_failed",
        },
    )


async def test_two_attempt_cap_message_fences_and_single_notice(store):
    api, user, other, clock = store
    handoff, target = await confirmed(api, user)
    first = await api.claim_handoff_execution(user, handoff, "one", execution_session_id=target)
    token = first["handoff"]["execution_claim_token"]
    args = (user, handoff, token, "user", "Fictional carried request", "telegram")
    message = await api.append_handoff_execution_message(*args)
    assert message == await api.append_handoff_execution_message(*args)
    assert not await api.append_handoff_execution_message(
        other, handoff, token, "user", "Fictional carried request", "telegram"
    )
    assert not await api.append_handoff_execution_message(
        user, handoff, token, "user", "Replacement content", "telegram"
    )
    assert await api.get_session_messages(target, exclude_message_id=message["message_id"]) == []
    clock["now"] += timedelta(minutes=6)
    assert not await api.append_handoff_execution_message(*args)
    second = await api.claim_handoff_execution(user, handoff, "two")
    new_args = (user, handoff, second["handoff"]["execution_claim_token"], *args[3:])
    assert await api.append_handoff_execution_message(*new_args) == message
    clock["now"] += timedelta(minutes=6)
    assert await api.claim_handoff_execution(user, handoff, "three") == {
        "status": "unavailable", "terminal": True
    }
    assert len(await api.get_session_messages(target)) == 1
    assert not await api.claim_handoff_failure_notice(other, handoff)
    assert await api.claim_handoff_failure_notice(user, handoff)
    assert not await api.claim_handoff_failure_notice(user, handoff)
    assert not await api.list_pending_handoff_failure_notices()
