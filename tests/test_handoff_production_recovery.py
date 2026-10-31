"""Production maintenance drains terminal notices and unavailable-owner queue rows."""

from unittest.mock import AsyncMock

import pytest

from src.agent.runtime import FAILURE_REPLY
from src.bot.update_claims import ChannelUpdateCoordinator
from tests.test_mode_conversation_store import confirmed
from tests.test_mode_routing import env as env  # noqa: F401 - both channel capabilities


async def wire_main(env, monkeypatch):
    from src import main

    monkeypatch.setattr(main, "store", env.store)
    monkeypatch.setattr(main, "channel", env.channel)
    monkeypatch.setattr(main, "handlers", env.handlers)
    monkeypatch.setattr(main, "handlers_by_channel", {env.channel.channel_id: env.handlers})
    monkeypatch.setattr(main, "update_coordinator", ChannelUpdateCoordinator(env.store))
    return main


@pytest.mark.parametrize("execution_scan_fails", [False, True])
async def test_production_scan_recovers_failure_notice_once_even_if_execution_scan_fails(
    env,
    monkeypatch,
    execution_scan_fails,
):
    main = await wire_main(env, monkeypatch)
    owner = env.user["user_id"]
    handoff, target = await confirmed(env.store, owner)
    claimed = await env.store.claim_handoff_execution(
        owner, handoff, "fixture", execution_session_id=target
    )
    assert await env.store.fail_handoff_execution(
        owner, handoff, claimed["handoff"]["execution_claim_token"], "execution_failed"
    )
    if execution_scan_fails:
        monkeypatch.setattr(
            env.store,
            "list_pending_handoff_executions",
            AsyncMock(side_effect=RuntimeError("private SQL error")),
        )
    await main._recover_pending_handoffs()
    await main._recover_pending_handoffs()
    assert sum(message["text"] == FAILURE_REPLY for message in env.channel.sent) == 1
    assert not await env.store.list_pending_handoff_failure_notices()
    assert not env.store.messages
    assert not env.script.requests


async def test_inactive_owners_drain_first_page_without_sends_or_target_sessions(env, monkeypatch):
    main = await wire_main(env, monkeypatch)
    owner, active = env.user["user_id"], env.other["user_id"]
    blocked = [await confirmed(env.store, owner) for _ in range(25)]
    eligible, _ = await confirmed(env.store, active)
    sessions_before = len(env.store.sessions)
    monkeypatch.setattr(
        env.store,
        "get_activation_state",
        AsyncMock(
            side_effect=lambda auth_id: {"completed": auth_id == env.other["supabase_auth_id"]}
        ),
    )
    execute = AsyncMock()
    monkeypatch.setattr(env.handlers.handoffs, "execute", execute)
    await main._recover_pending_handoffs()
    remaining = await env.store.list_pending_handoff_executions()
    assert [row["handoff_id"] for row in remaining] == [eligible]
    await main._recover_pending_handoffs()
    assert execute.await_count == 1 and execute.await_args.args[0]["user_id"] == active
    for handoff, _ in blocked:
        row = env.store._mode_state.handoffs[handoff]
        assert row["execution_failed_at"]
        assert row["execution_failure_notice_outcome"] == "owner_unavailable"
    assert len(env.store.sessions) == sessions_before
    assert not env.channel.sent and not env.script.requests


async def test_inactive_owner_notice_is_consumed_without_topic_creation(env, monkeypatch):
    main = await wire_main(env, monkeypatch)
    owner = env.user["user_id"]
    handoff, target = await confirmed(env.store, owner)
    claimed = await env.store.claim_handoff_execution(
        owner, handoff, "fixture", execution_session_id=target
    )
    await env.store.fail_handoff_execution(
        owner, handoff, claimed["handoff"]["execution_claim_token"], "execution_failed"
    )
    monkeypatch.setattr(
        env.store, "get_activation_state", AsyncMock(return_value={"completed": False})
    )
    create = AsyncMock(wraps=env.channel.create_conversation)
    monkeypatch.setattr(env.channel, "create_conversation", create)
    await main._recover_pending_handoffs()
    create.assert_not_awaited()
    assert not env.channel.sent
    assert not await env.store.list_pending_handoff_failure_notices()


async def test_unavailable_retirement_does_not_steal_live_worker_lease(env):
    owner = env.user["user_id"]
    handoff, target = await confirmed(env.store, owner)
    claimed = await env.store.claim_handoff_execution(
        owner, handoff, "live", execution_session_id=target
    )
    await env.handlers.handoffs.retire_unavailable(
        {"user_id": owner, "handoff_id": handoff, "execution_session_id": target},
        "owner_unavailable",
    )
    row = env.store._mode_state.handoffs[handoff]
    assert not row["execution_failed_at"] and not row["execution_failure_notice_at"]
    assert row["execution_claim_token"] == claimed["handoff"]["execution_claim_token"]
