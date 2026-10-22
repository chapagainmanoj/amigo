"""Channel-neutral conversations, isolated Sessions, durable fenced handoff execution."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.memory.memory_store import InMemoryStore
from src.memory.store import MemoryStore
from tests.fakes import FakeStore


@pytest.fixture(params=[InMemoryStore, FakeStore])
async def store(request, monkeypatch):
    clock = {"now": datetime(2026, 10, 22, 12)}
    monkeypatch.setattr("src.memory.modes.utc_now", lambda: clock["now"])
    monkeypatch.setattr("src.memory.memory_store.utc_now", lambda: clock["now"])
    monkeypatch.setattr("tests.fakes.utc_now", lambda: clock["now"])
    result = request.param()
    user = await result.create_user(17001)
    other = await result.create_user(17002)
    return result, user["user_id"], other["user_id"], clock


async def test_canonical_and_aliases_unique_across_owners_modes_and_channels(store):
    api, user, other, _ = store
    first = {"chat_id": 17001, "thread_id": 10}
    alias = {"chat_id": 17001, "thread_id": 11}
    await api.save_mode_conversation(user, "daily", "telegram", first)
    await api.save_mode_conversation(user, "daily", "telegram", alias, alias=True)
    assert (await api.get_mode_conversation(user, "daily", "telegram"))["endpoint"] == first
    assert await api.get_mode_by_conversation(user, "telegram", alias) == "daily"
    assert await api.get_mode_by_conversation(other, "telegram", alias) is None
    assert await api.get_mode_by_conversation(user, "whatsapp", alias) is None
    for owner, mode in [(other, "daily"), (user, "coach")]:
        with pytest.raises(ValueError):
            await api.save_mode_conversation(owner, mode, "telegram", alias)
    rows = await api.list_mode_conversations(user)
    rows[0]["endpoint"]["thread_id"] = -1
    assert (await api.get_mode_conversation(user, "daily", "telegram"))["endpoint"] == first
    await api.save_mode_conversation(user, "daily", "telegram", alias)
    assert await api.get_mode_by_conversation(user, "telegram", first) == "daily"
    assert (await api.get_mode_conversation(user, "daily", "telegram"))["endpoint"] == first
    await api.close_mode_conversation(user, "daily", "telegram")
    assert await api.get_mode_conversation(user, "daily", "telegram") is None
    # Closed specialized conversations remain identifiable for the withdrawal notice.
    assert await api.get_mode_by_conversation(user, "telegram", alias) == "daily"
    assert len(await api.list_mode_conversations()) == 1


async def test_alias_without_canonical_becomes_canonical_and_sessions_isolate(store):
    api, user, _, _ = store
    await api.save_mode_conversation(user, "daily", "cli", {"recipient": "local"}, alias=True)
    assert await api.get_mode_conversation(user, "daily", "cli")
    coach = await api.create_session(user, mode_id="coach")
    daily = await api.create_session(user)
    assert coach["mode_id"] == coach["active_mode_id"] == "coach"
    assert daily["mode_id"] == "daily" and daily["active_mode_id"] is None
    assert (await api.get_active_session(user))["session_id"] == daily["session_id"]
    assert (await api.get_active_session(user, "coach"))["session_id"] == coach["session_id"]
    assert not await api.has_session_on_local_day(user, "UTC", mode_id="reflect")
    assert await api.get_yesterday_summary(user, "UTC", mode_id="coach") is None
    assert (await api.get_user_by_id(user))["telegram_chat_id"] == 17001
    assert await api.get_user_by_id("missing") is None


async def confirmed(api, user):
    source = await api.create_session(user, mode_id="coach")
    target = await api.create_session(user)
    await api.grant_mode(user, "coach", "owner", "trial")
    pending = await api.create_handoff(user, source["session_id"], "coach", "daily", "Add milk")
    handoff_id = pending["handoff"]["handoff_id"]
    assert (await api.resolve_handoff(user, source["session_id"], handoff_id, True))[
        "status"
    ] == "confirmed"
    return handoff_id, target["session_id"]


async def test_execution_single_claim_recovery_clock_plan_fencing_and_completion(store):
    api, user, other, clock = store
    handoff, target = await confirmed(api, user)
    assert await api.claim_handoff_execution(
        other, handoff, "wrong", execution_session_id=target
    ) == {"status": "unavailable"}
    results = await asyncio.gather(
        *(
            api.claim_handoff_execution(user, handoff, "worker", execution_session_id=target)
            for _ in range(3)
        )
    )
    assert sorted(item["status"] for item in results) == ["busy", "busy", "claimed"]
    row = next(item["handoff"] for item in results if item["status"] == "claimed")
    token = row["execution_claim_token"]
    plan = [{"parts": [{"tool": "create_task", "args": {"title": "milk"}}]}]
    assert await api.save_handoff_execution_plan(user, handoff, token, plan)
    assert await api.save_handoff_execution_plan(user, handoff, token, plan)
    assert not await api.save_handoff_execution_plan(user, handoff, token, [])
    assert not await api.save_handoff_execution_plan(user, handoff, token, [{"changed": True}])
    assert await api.list_pending_handoff_executions() == []
    clock["now"] += timedelta(minutes=5)
    assert not await api.complete_handoff_execution(user, handoff, token)
    recovery = await api.list_pending_handoff_executions()
    assert recovery[0]["handoff_id"] == handoff
    assert "carried_request" not in recovery[0]
    retry = await api.claim_handoff_execution(user, handoff, "recovery")
    assert retry["handoff"]["execution_session_id"] == target
    assert retry["handoff"]["execution_plan"] == plan
    assert retry["handoff"]["execution_clock_at"] == row["execution_clock_at"]
    assert retry["handoff"]["execution_attempts"] == 2
    new_token = retry["handoff"]["execution_claim_token"]
    assert token != new_token
    assert not await api.save_handoff_execution_plan(
        user, handoff, token, plan + [{"text": "late"}]
    )
    assert not await api.complete_handoff_execution(other, handoff, new_token)
    assert await api.complete_handoff_execution(user, handoff, new_token)
    assert not await api.complete_handoff_execution(user, handoff, new_token)
    assert await api.claim_handoff_execution(user, handoff, "late") == {"status": "executed"}


async def test_bound_session_cannot_change_and_survives_closed_session_rollover(store):
    api, user, _, clock = store
    handoff, target = await confirmed(api, user)
    first = await api.claim_handoff_execution(user, handoff, "worker", execution_session_id=target)
    assert first["status"] == "claimed"
    clock["now"] += timedelta(minutes=6)
    replacement = await api.create_session(user)
    assert await api.claim_handoff_execution(
        user,
        handoff,
        "retry",
        execution_session_id=replacement["session_id"],
    ) == {"status": "unavailable"}
    await api.close_session(target)
    recovered = await api.claim_handoff_execution(user, handoff, "retry")
    assert recovered["status"] == "claimed"
    assert recovered["handoff"]["execution_session_id"] == target
    assert recovered["handoff"]["execution_attempts"] == 2
    # New claims may not bind an already closed Session.
    second, second_target = await confirmed(api, user)
    await api.close_session(second_target)
    assert await api.claim_handoff_execution(
        user,
        second,
        "first",
        execution_session_id=second_target,
    ) == {"status": "unavailable"}


async def test_supabase_execution_and_conversation_rpc_contract():
    api = MemoryStore()
    query = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(data=True)))
    api.db = SimpleNamespace(rpc=Mock(return_value=query))
    endpoint = {"chat_id": 1, "thread_id": 2}
    await api.save_mode_conversation("u", "daily", "telegram", endpoint, alias=True)
    api.db.rpc.assert_called_with(
        "save_mode_conversation",
        {
            "p_user_id": "u",
            "p_mode_id": "daily",
            "p_channel": "telegram",
            "p_endpoint": endpoint,
            "p_alias": True,
        },
    )
    await api.claim_handoff_execution("u", "h", "worker", execution_session_id="s")
    api.db.rpc.assert_called_with(
        "claim_handoff_execution",
        {
            "p_user_id": "u",
            "p_handoff_id": "h",
            "p_worker_id": "worker",
            "p_execution_session_id": "s",
        },
    )
    assert await api.save_handoff_execution_plan("u", "h", "token", [{"text": "step"}])
    api.db.rpc.assert_called_with(
        "save_handoff_execution_plan",
        {
            "p_user_id": "u",
            "p_handoff_id": "h",
            "p_claim_token": "token",
            "p_plan": [{"text": "step"}],
        },
    )


@pytest.mark.parametrize(
    "endpoint,equivalent",
    [
        ({"address": 1}, {"address": 1.0}),
        ({"address": 10**23}, {"address": 1e23}),
        ({"nested": {"parts": [1, {"number": 0}]}}, {"nested": {"parts": [1.0, {"number": -0.0}]}}),
    ],
)
async def test_endpoint_jsonb_numeric_identity_prevents_cross_owner_reassignment(
    store,
    endpoint,
    equivalent,
):
    api, user, other, _ = store
    await api.save_mode_conversation(user, "daily", "telegram", endpoint)
    assert await api.get_mode_by_conversation(user, "telegram", equivalent) == "daily"
    with pytest.raises(ValueError, match="already assigned"):
        await api.save_mode_conversation(other, "coach", "telegram", equivalent, alias=True)


async def test_supabase_conversation_reads_and_sessions_filter_owner_and_mode():
    import json

    query = Mock()
    for method in ["select", "eq", "is_", "order", "limit", "maybe_single", "gte", "lt"]:
        getattr(query, method).return_value = query
    query.not_ = query
    query.execute = AsyncMock(
        return_value=SimpleNamespace(data={"mode_id": "coach", "context_summary": "Coach summary"})
    )
    api = MemoryStore()
    api.db = SimpleNamespace(table=Mock(return_value=query))
    await api.get_active_session("owner", "coach")
    query.eq.assert_any_call("user_id", "owner")
    query.eq.assert_any_call("mode_id", "coach")
    query.reset_mock()
    await api.get_mode_conversation("owner", "coach", "telegram")
    query.eq.assert_any_call("user_id", "owner")
    query.eq.assert_any_call("mode_id", "coach")
    query.eq.assert_any_call("channel", "telegram")
    query.is_.assert_called_with("closed_at", "null")
    endpoint = {"chat_id": 1, "thread_id": 10}
    query.reset_mock()
    assert await api.get_mode_by_conversation("owner", "telegram", endpoint) == "coach"
    query.eq.assert_any_call("user_id", "owner")
    query.eq.assert_any_call("endpoint", json.dumps(endpoint, sort_keys=True))
    query.reset_mock()
    await api.has_session_on_local_day("owner", "UTC", "coach")
    query.eq.assert_any_call("user_id", "owner")
    query.eq.assert_any_call("mode_id", "coach")
    query.reset_mock()
    await api.get_yesterday_summary("owner", "UTC", "coach")
    query.eq.assert_any_call("user_id", "owner")
    query.eq.assert_any_call("mode_id", "coach")


async def test_summaries_and_local_day_reads_do_not_cross_modes(store, monkeypatch):
    from src.utils import Clock

    class FixedDay(Clock):
        def utc_now(self):
            return datetime(2026, 10, 22, 12)

    monkeypatch.setattr("src.utils.default_clock", FixedDay())
    api, user, _, clock = store
    clock["now"] = datetime(2026, 10, 21, 12)
    coach = await api.create_session(user, mode_id="coach")
    await api.close_session(coach["session_id"], "Coach-only summary")
    assert await api.get_yesterday_summary(user, "UTC", "coach") == "Coach-only summary"
    assert await api.get_yesterday_summary(user, "UTC") is None
    assert not await api.has_session_on_local_day(user, "UTC", "coach")
    clock["now"] = datetime(2026, 10, 22, 12)
    await api.create_session(user, mode_id="coach")
    assert await api.has_session_on_local_day(user, "UTC", "coach")
    assert not await api.has_session_on_local_day(user, "UTC")


async def test_durable_plan_uses_jsonb_equality_not_python_bool_number_equality(store):
    api, user, _, _ = store
    handoff, target = await confirmed(api, user)
    claim = await api.claim_handoff_execution(user, handoff, "worker", execution_session_id=target)
    token = claim["handoff"]["execution_claim_token"]
    assert await api.save_handoff_execution_plan(user, handoff, token, [{"flag": True, "count": 1}])
    assert not await api.save_handoff_execution_plan(
        user, handoff, token, [{"flag": 1, "count": 1}]
    )
    assert await api.save_handoff_execution_plan(
        user, handoff, token, [{"flag": True, "count": 1.0}]
    )


async def test_handoff_command_receipt_lookup_is_owned_and_detached(store):
    api, user, other, _ = store
    from src.commands.base import CommandContext
    from src.commands.tasks import CreateTaskCommand, CreateTaskInput

    result = await CreateTaskCommand(api).run(
        CommandContext(user, "telegram", "handoff:receipt-test"), CreateTaskInput("fictional")
    )
    receipt = await api.get_command_receipt(user, "handoff:receipt-test")
    assert receipt["result"] == result
    assert await api.get_command_receipt(other, "handoff:receipt-test") is None
    receipt["result"]["task"]["title"] = "tampered"
    assert (await api.get_command_receipt(user, "handoff:receipt-test"))["result"] == result


async def test_adapter_receipt_lookup_filters_participant_and_exact_key():
    query = Mock()
    for name in ("select", "eq", "maybe_single"):
        getattr(query, name).return_value = query
    query.execute = AsyncMock(return_value=SimpleNamespace(data={"result": {"task": "owned"}}))
    api = MemoryStore()
    api.db = SimpleNamespace(table=Mock(return_value=query))
    assert await api.get_command_receipt("owner", "stable-key") == {"result": {"task": "owned"}}
    api.db.table.assert_called_once_with("command_receipts")
    assert query.eq.call_args_list == [
        (("user_id", "owner"),), (("idempotency_key", "stable-key"),)
    ]
