"""Review item3: bounded executions, one logical transcript and durable failure notice attempts."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.models.function import FunctionModel

from src.agent.runtime import FAILURE_REPLY
from tests.test_mode_routing import env as env  # noqa: F401 - threaded/command application fixture
from tests.test_mode_routing import propose


async def test_failed_execution_stops_after_two_attempts_and_one_failure_notice(env):
    row, confirm, _ = await propose(env)
    await env.callback(confirm)  # Empty scripted provider fails without a real model call.
    assert row["execution_attempts"] == 1
    assert not [message for message in env.channel.sent if message["text"] == FAILURE_REPLY]
    env.clock.now += timedelta(minutes=6)
    async with env.runtime.override(model=FunctionModel(env.script.respond)):
        await env.handlers.handoffs.recover()
    assert row["execution_attempts"] == 2 and row["execution_failed_at"]
    assert row["execution_failure_notice_at"]
    assert len([message for message in env.channel.sent if message["text"] == FAILURE_REPLY]) == 1
    calls = len(env.script.requests)
    env.clock.now += timedelta(minutes=6)
    async with env.runtime.override(model=FunctionModel(env.script.respond)):
        await env.handlers.handoffs.recover()
    await env.callback(confirm)
    assert len(env.script.requests) == calls
    assert len([message for message in env.channel.sent if message["text"] == FAILURE_REPLY]) == 1


async def test_ensure_failure_is_caught_and_second_attempt_can_succeed(env, monkeypatch):
    row, confirm, _ = await propose(env)
    original = env.handlers.handoffs.conversations.ensure
    monkeypatch.setattr(
        env.handlers.handoffs.conversations, "ensure", AsyncMock(side_effect=RuntimeError)
    )
    await env.callback(confirm)
    assert row["execution_attempts"] == 1 and row["executed_at"] is None
    monkeypatch.setattr(env.handlers.handoffs.conversations, "ensure", original)
    env.clock.now += timedelta(minutes=6)
    env.script.text("Recovered target reply.")
    async with env.runtime.override(model=FunctionModel(env.script.respond)):
        await env.handlers.handoffs.recover()
    assert row["executed_at"] and row["execution_attempts"] == 2


async def test_crash_recovery_carries_user_message_once_in_store_and_model_history(
    env, monkeypatch
):
    row, confirm, _ = await propose(env)
    env.script.tool("create_task", {"title": "milk"})
    original = env.store.create_task_command

    async def commit_then_crash(*args, **kwargs):
        await original(*args, **kwargs)
        raise asyncio.CancelledError

    monkeypatch.setattr(env.store, "create_task_command", commit_then_crash)
    with pytest.raises(asyncio.CancelledError):
        await env.callback(confirm)
    monkeypatch.setattr(env.store, "create_task_command", original)
    env.clock.now += timedelta(minutes=6)
    env.script.text("Saved before the crash.")
    async with env.runtime.override(model=FunctionModel(env.script.respond)):
        await env.handlers.handoffs.recover()
    messages = await env.store.get_session_messages(row["execution_session_id"])
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert env.script.requests[-1]["history"].count("Participant-confirmed handoff request") == 1
    assert len(env.store.tasks) == 1


async def test_owned_expired_buttons_are_removed_foreign_buttons_are_untouched(env):
    row, confirm, _ = await propose(env)
    before = len(env.channel.edited)
    await env.callback(confirm, chat_id=41002)
    assert len(env.channel.edited) == before
    env.clock.now += timedelta(minutes=11)
    await env.callback(confirm)
    assert row["resolution"] == "expired"
    assert len(env.channel.edited) == before + 1
    assert env.channel.edited[-1]["buttons"] is None


async def test_recovery_continues_after_a_different_row_lookup_fails(env, monkeypatch):
    row, _, _ = await propose(env)
    await env.store.resolve_handoff(env.user["user_id"], row["session_id"], row["handoff_id"], True)
    pending = await env.store.list_pending_handoff_executions()
    monkeypatch.setattr(
        env.store,
        "list_pending_handoff_executions",
        AsyncMock(
            return_value=[
                {"user_id": "broken-owner", "handoff_id": "broken"},
                *pending,
            ]
        ),
    )
    original = env.store.get_user_by_id

    async def get_user(user_id):
        if user_id == "broken-owner":
            raise RuntimeError("private failure")
        return await original(user_id)

    monkeypatch.setattr(env.store, "get_user_by_id", get_user)
    env.script.text("Recovered later row.")
    async with env.runtime.override(model=FunctionModel(env.script.respond)):
        await env.handlers.handoffs.recover()
    assert row["executed_at"] is not None
