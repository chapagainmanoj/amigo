"""Both channel capabilities exercise the same Mode, history and durable handoff contract."""

import asyncio
from collections import deque
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from src.agent.catalogue import DAILY
from src.agent.registry import ModeRegistry
from src.agent.runtime import ModeRuntime
from src.bot.handlers import BotHandlers
from src.channels.base import ConversationRef
from src.config import Settings
from src.memory.sessions import SessionManager
from src.utils import Clock
from tests.fakes import FakeChannel, FakeScheduler, FakeStore
from tests.test_modes import _participant


class MutableClock(Clock):
    def __init__(self):
        self.now = datetime(2026, 10, 22, 10)

    def utc_now(self):
        return self.now


class Script:
    def __init__(self):
        self.responses = deque()
        self.requests = []

    async def respond(self, messages, info):
        self.requests.append(
            {
                "history": ModelMessagesTypeAdapter.dump_json(messages).decode(),
                "instructions": info.instructions,
                "tools": {tool.name for tool in info.function_tools},
            }
        )
        if not self.responses:
            raise AssertionError("Unexpected model request")
        return self.responses.popleft()

    def text(self, text="Acknowledged."):
        self.responses.append(ModelResponse(parts=[TextPart(text)], model_name="scripted-routing"))

    def tool(self, name, args, *, call_id="step-1"):
        self.responses.append(
            ModelResponse(
                parts=[ToolCallPart(name, args, tool_call_id=call_id)],
                model_name="scripted-routing",
            )
        )


@pytest.fixture(params=[False, True], ids=["commands", "threaded"])
async def env(request, monkeypatch):
    clock = MutableClock()
    monkeypatch.setattr("src.config.settings", Settings(_env_file=None))
    for module in ("src.memory.modes", "tests.fakes"):
        monkeypatch.setattr(f"{module}.utc_now", clock.utc_now)
    store = FakeStore()
    user = await _participant(store, 41001, link="fake")
    other = await _participant(store, 41002, link="fake")
    monkeypatch.setattr(store, "get_activation_state", AsyncMock(return_value={"completed": True}))
    coach = replace(
        DAILY,
        id="coach",
        name="Coach",
        purpose="One bounded coaching question.",
        instructions=lambda facts: "COACH PRIVATE CONTRACT: ask one practical coaching question.",
        toolsets=(),
        tool_order=(),
        context=(),
        handoffs=("daily",),
        entitlement="grant",
    )
    runtime = ModeRuntime(ModeRegistry((DAILY, coach)))
    channel = FakeChannel(threads=request.param, channel_id="fake")
    handlers = BotHandlers(
        channel,
        store,
        SessionManager(store, clock),
        FakeScheduler(),
        mode_runtime=runtime,
    )
    monkeypatch.setattr(handlers, "_is_allowed", AsyncMock(return_value=True))
    await store.grant_mode(user["user_id"], "coach", "owner", "fictional routing evaluation")
    script = Script()
    state = SimpleNamespace(
        store=store,
        user=user,
        other=other,
        runtime=runtime,
        channel=channel,
        handlers=handlers,
        clock=clock,
        script=script,
        update_id=0,
    )

    async def send(text, conversation=None):
        state.update_id += 1
        async with runtime.override(model=FunctionModel(script.respond)):
            await handlers.handle_message(
                41001, text, update_id=state.update_id, conversation=conversation
            )

    async def enter(mode):
        await send("/daily" if mode == "daily" else f"/mode {mode}")
        return await handlers.turn_processor.modes.conversations.ensure(user, mode, chat_id=41001)

    async def callback(data, *, chat_id=41001, conversation=None):
        async with runtime.override(model=FunctionModel(script.respond)):
            await handlers.handle_callback(chat_id, 1, data, conversation=conversation)

    state.send, state.enter, state.callback = send, enter, callback
    return state


async def propose(env):
    coach_ref = await env.enter("coach")
    env.script.tool("propose_handoff", {"target_mode_id": "daily", "carried_request": "Add milk"})
    env.script.text("Confirm to pass that request.")
    await env.send("Pass my request to Daily", coach_ref)
    proposal = next(message for message in reversed(env.channel.sent) if message["buttons"])
    confirm, decline = [button["callback_data"] for button in proposal["buttons"][0]]
    assert len(confirm.encode()) <= 64
    assert len(decline.encode()) <= 64
    row = list(env.store._mode_state.handoffs.values())[-1]
    assert row["resolution"] is None
    assert not env.store.tasks
    return row, confirm, decline


async def test_mode_commands_are_model_free_and_both_entry_paths_choose_coach(env, caplog):
    ref = await env.enter("coach")
    assert not env.script.requests
    env.script.text("One coaching question.")
    with caplog.at_level("INFO"):
        await env.send("Coach-only input", ref)
    record = next(item.turn_record for item in caplog.records if hasattr(item, "turn_record"))
    assert record["mode_id"] == "coach"
    assert record["entered_by"] == ("topic" if env.channel.capabilities.threads else "command")
    sessions = [row for row in env.store.sessions if row["mode_id"] == "coach"]
    assert len(sessions) == 1
    assert env.script.requests[0]["tools"] == {"propose_handoff"}
    assert "COACH PRIVATE CONTRACT" in env.script.requests[0]["instructions"]
    assert env.channel.sent[-1].get("conversation") == ref
    await env.enter("daily")
    await env.send("/mode")
    assert "You're in Daily" in env.channel.last_text
    assert len(env.script.requests) == 1


async def test_unknown_conversations_are_daily_aliases_without_replacing_canonical(env):
    if not env.channel.capabilities.threads:
        await env.enter("daily")
        env.script.text()
        await env.send("Daily by command")
        assert env.script.requests[-1]["tools"] != {"propose_handoff"}
        return
    canonical = await env.enter("daily")
    for value in (101, 102):
        unknown = ConversationRef("fake", {"chat_id": 41001, "conversation_id": value})
        env.script.text()
        await env.send("Daily in an unknown conversation", unknown)
        assert env.channel.sent[-1]["conversation"] == unknown
        assert (
            await env.store.get_mode_by_conversation(
                env.user["user_id"],
                "fake",
                dict(unknown.endpoint),
            )
            == "daily"
        )
    stored = await env.store.get_mode_conversation(env.user["user_id"], "daily", "fake")
    assert stored["endpoint"] == dict(canonical.endpoint)
    assert len([row for row in env.store.sessions if row["mode_id"] == "daily"]) == 1


async def test_coach_and_daily_histories_never_cross_session_boundary(env):
    coach_ref = await env.enter("coach")
    env.script.text("Coach-only reply sentinel")
    await env.send("Coach-only input sentinel", coach_ref)
    daily_ref = await env.enter("daily")
    env.script.text("Daily-only reply sentinel")
    await env.send("Daily-only input sentinel", daily_ref)
    assert "Coach-only" not in env.script.requests[-1]["history"]
    coach_ref = await env.enter("coach")
    env.script.text("Coach continues.")
    await env.send("Resume coaching", coach_ref)
    history = env.script.requests[-1]["history"]
    assert "Coach-only input sentinel" in history
    assert "Coach-only reply sentinel" in history
    assert "Daily-only" not in history


@pytest.mark.parametrize("withdrawal", ["grant", "catalogue"])
async def test_withdrawn_mode_sends_notice_without_running_daily(env, withdrawal):
    ref = await env.enter("coach")
    if withdrawal == "grant":
        await env.store.revoke_mode_grant(
            env.user["user_id"], "coach", "owner", "fixture withdrawal"
        )
    else:
        coach = await env.runtime.registry.get("coach")
        env.runtime.registry = ModeRegistry((DAILY, replace(coach, status="disabled")))
    await env.send("Resume coaching", ref)
    assert not env.script.requests
    assert "isn't available" in env.channel.last_text
    assert env.channel.sent[-1].get("conversation") == ref
    assert not env.store.messages


async def test_confirm_runs_one_target_turn_and_double_tap_is_inert(env):
    row, confirm, _ = await propose(env)
    env.script.tool("create_task", {"title": "milk"})
    env.script.text("Milk added.")
    await env.callback(confirm)
    calls = len(env.script.requests)
    assert len(env.store.tasks) == 1
    assert row["executed_at"] is not None
    target = row["execution_session_id"]
    assert env.store.tasks[0]["source_session_id"] == target
    assert (
        next(session for session in env.store.sessions if session["session_id"] == target)[
            "mode_id"
        ]
        == "daily"
    )
    await env.callback(confirm)
    assert len(env.script.requests) == calls
    assert len(env.store.tasks) == 1
    assert "untrusted" in env.script.requests[-2]["history"]
    assert "COACH PRIVATE CONTRACT" not in env.script.requests[-2]["instructions"]
    if env.channel.capabilities.threads:
        assert env.channel.sent[-1][
            "conversation"
        ] == await env.handlers.turn_processor.modes.conversations.ensure(env.user)


@pytest.mark.parametrize("outcome", ["decline", "expired", "cross-user"])
async def test_handoff_other_resolutions_never_run_target(env, outcome):
    row, confirm, decline = await propose(env)
    calls = len(env.script.requests)
    if outcome == "expired":
        env.clock.now += timedelta(minutes=11)
        await env.callback(confirm)
        assert row["resolution"] == "expired"
    elif outcome == "cross-user":
        await env.callback(confirm, chat_id=41002)
        assert row["resolution"] is None
    else:
        await env.callback(decline)
        await env.callback(confirm)
        assert row["resolution"] == "declined"
    assert len(env.script.requests) == calls
    assert not env.store.tasks


@pytest.mark.parametrize("crash_point", ["after-plan", "after-task-commit"])
async def test_handoff_crash_replays_plan_without_duplicate_task_or_changing_clock_session(
    env,
    monkeypatch,
    crash_point,
):
    row, confirm, _ = await propose(env)
    env.script.tool("create_task", {"title": "milk"}, call_id="stable-create-call")
    method = "save_handoff_execution_plan" if crash_point == "after-plan" else "create_task_command"
    original = getattr(env.store, method)

    async def commit_then_crash(*args, **kwargs):
        await original(*args, **kwargs)
        raise asyncio.CancelledError

    monkeypatch.setattr(env.store, method, commit_then_crash)
    with pytest.raises(asyncio.CancelledError):
        await env.callback(confirm)
    assert len(row["execution_plan"]) == 1
    assert len(env.store.tasks) == (0 if crash_point == "after-plan" else 1)
    bound_session, bound_clock = row["execution_session_id"], row["execution_clock_at"]
    original_token = row["execution_claim_token"]
    monkeypatch.setattr(env.store, method, original)
    await env.store.close_session(bound_session)
    env.clock.now += timedelta(days=1)
    env.script.text("Milk added after recovery.")
    async with env.runtime.override(model=FunctionModel(env.script.respond)):
        await env.handlers.handoffs.recover()
    assert len(env.store.tasks) == 1
    task = env.store.tasks[0]
    assert task["source_session_id"] == bound_session
    assert row["execution_session_id"] == bound_session
    assert row["execution_clock_at"] == bound_clock
    assert row["execution_claim_token"] != original_token
    assert row["execution_attempts"] == 2
    assert row["executed_at"] is not None
    assert (
        len(env.script.requests) == 4
    )  # two proposal steps, one original Tool step, one new reply
    assert env.channel.last_text == "Milk added after recovery."
    original_time, recovered_time = [
        next(
            line
            for line in request["instructions"].splitlines()
            if line.startswith("Current local time")
        )
        for request in (env.script.requests[2], env.script.requests[3])
    ]
    assert original_time == recovered_time
    assert "2026-10-22 15:45" in original_time


async def test_coach_can_propose_again_in_same_session_after_handoff(env):
    first, confirm, _ = await propose(env)
    env.script.text("Daily acknowledged.")
    await env.callback(confirm)
    second, _, decline = await propose(env)
    assert first["handoff_id"] != second["handoff_id"]
    assert first["session_id"] == second["session_id"]
    assert first["executed_at"] is not None
    await env.callback(decline)
    assert second["resolution"] == "declined"


async def test_racing_confirmation_callbacks_execute_exactly_one_target_turn(env):
    row, confirm, _ = await propose(env)
    env.script.tool("create_task", {"title": "milk"})
    env.script.text("Milk added.")
    await asyncio.gather(env.callback(confirm), env.callback(confirm))
    assert len(env.store.tasks) == 1
    assert row["execution_attempts"] == 1
    assert row["executed_at"] is not None
    assert len(env.script.requests) == 4


async def test_undeclared_handoff_target_never_creates_proposal(env):
    ref = await env.enter("coach")
    env.script.tool(
        "propose_handoff", {"target_mode_id": "coach", "carried_request": "No transfer"}
    )
    env.script.text("That transfer is unavailable.")
    await env.send("Try an undeclared target", ref)
    assert not env.store._mode_state.handoffs
    assert not any(message["buttons"] for message in env.channel.sent)
    assert not env.store.tasks


@pytest.mark.parametrize(
    "existing_reminder", [False, True], ids=["create-and-schedule", "reschedule"]
)
@pytest.mark.parametrize(
    "change_preferences", [False, True], ids=["same-profile", "changed-profile"]
)
async def test_handoff_reminder_commit_crash_reuses_exact_owned_receipt(
    env,
    monkeypatch,
    existing_reminder,
    change_preferences,
):
    row, confirm, _ = await propose(env)
    if existing_reminder:
        task = await env.store.create_task(env.user["user_id"], "milk")
        task["due_date"] = None
        await env.store.create_reminder(
            task["task_id"],
            env.user["user_id"],
            (env.clock.now + timedelta(minutes=20)).isoformat(),
        )
        env.script.tool(
            "schedule_reminder",
            {
                "task_id": task["task_id"],
                "time_expression": "in 30 minutes",
            },
        )
    else:
        env.script.tool("create_task", {"title": "milk", "reminder_time": "in 30 minutes"})
    original = env.store.schedule_reminder_command

    async def commit_then_crash(*args, **kwargs):
        await original(*args, **kwargs)
        raise asyncio.CancelledError

    monkeypatch.setattr(env.store, "schedule_reminder_command", commit_then_crash)
    with pytest.raises(asyncio.CancelledError):
        await env.callback(confirm)
    reminder_ids = {reminder["reminder_id"] for reminder in env.store.reminders}
    assert len(reminder_ids) == (2 if existing_reminder else 1)
    active = [reminder for reminder in env.store.reminders if reminder["status"] == "pending"]
    assert len(active) == 1
    intended = active[0]["scheduled_time"]
    bound = row["execution_session_id"]
    replay_write = AsyncMock(wraps=original)
    monkeypatch.setattr(env.store, "schedule_reminder_command", replay_write)
    env.clock.now += timedelta(minutes=6)
    if change_preferences:
        await env.store.update_user(
            env.user["user_id"],
            {
                "timezone": "America/New_York",
                "wake_time": "10:00",
                "sleep_time": "20:00",
            },
        )
    env.script.text("Reminder saved before interruption.")
    async with env.runtime.override(model=FunctionModel(env.script.respond)):
        await env.handlers.handoffs.recover()
    assert row["executed_at"] is not None
    assert row["execution_session_id"] == bound
    assert len(env.store.tasks) == 1
    assert {reminder["reminder_id"] for reminder in env.store.reminders} == reminder_ids
    active = [reminder for reminder in env.store.reminders if reminder["status"] == "pending"]
    assert len(active) == 1 and active[0]["scheduled_time"] == intended
    replay_write.assert_not_awaited()
    assert env.channel.last_text == "Reminder saved before interruption."


async def test_handoff_target_becomes_next_command_channel_mode(env):
    row, confirm, _ = await propose(env)
    env.script.text("Daily acknowledges the confirmed handoff.")
    await env.callback(confirm)
    assert row["executed_at"] is not None
    env.script.text("Continuing in Daily.")
    target_ref = await env.handlers.turn_processor.modes.conversations.ensure(env.user)
    await env.send("Continue from the handoff", target_ref)
    assert "create_task" in env.script.requests[-1]["tools"]
    assert "propose_handoff" not in env.script.requests[-1]["tools"]
    assert "COACH PRIVATE CONTRACT" not in env.script.requests[-1]["instructions"]
    if env.channel.capabilities.threads:
        coach_ref = await env.handlers.turn_processor.modes.conversations.ensure(env.user, "coach")
        env.script.text("Coach remains independent.")
        await env.send("Continue in the original Coach conversation", coach_ref)
        assert env.script.requests[-1]["tools"] == {"propose_handoff"}
        assert "COACH PRIVATE CONTRACT" in env.script.requests[-1]["instructions"]


async def test_reusable_summary_provider_is_scoped_to_current_mode(env, monkeypatch):
    from src.agent.context import yesterday_summary

    async def summary(user_id, timezone, mode_id="daily"):
        return "DAILY PRIVATE SUMMARY" if mode_id == "daily" else "COACH PRIVATE SUMMARY"

    monkeypatch.setattr(env.store, "get_yesterday_summary", AsyncMock(side_effect=summary))
    coach = await env.runtime.registry.get("coach")
    env.runtime.registry = ModeRegistry((DAILY, replace(coach, context=(yesterday_summary,))))
    ref = await env.enter("coach")
    env.script.text("Coaching continues.")
    await env.send("Use only this Mode's summary", ref)
    instructions = env.script.requests[-1]["instructions"]
    assert "COACH PRIVATE SUMMARY" in instructions
    assert "DAILY PRIVATE SUMMARY" not in instructions
    ref = await env.enter("daily")
    env.script.text("Daily continues.")
    await env.send("Use Daily's own summary", ref)
    instructions = env.script.requests[-1]["instructions"]
    assert "DAILY PRIVATE SUMMARY" in instructions
    assert "COACH PRIVATE SUMMARY" not in instructions


async def test_durable_model_replay_retains_signed_gemini_parts_and_provider_metadata():
    from pydantic_ai.messages import ThinkingPart
    from pydantic_ai.models import ModelRequestParameters

    from src.tools.handoff_execution import DurableHandoffModel

    original = ModelResponse(
        parts=[
            ThinkingPart("", signature="b3BhcXVlLXNpZ25hdHVyZQ==", provider_name="google"),
            ToolCallPart(
                "create_task",
                {"title": "fictional milk"},
                tool_call_id="signed-call",
                provider_name="google",
                provider_details={"thought_signature": "c2lnbmF0dXJl"},
            ),
        ],
        model_name="gemini-3.5-flash",
        provider_name="google",
        provider_response_id="fictional-provider-response",
        provider_details={"traffic_type": "ON_DEMAND"},
    )
    store = SimpleNamespace(save_handoff_execution_plan=AsyncMock(return_value=True))
    handoff = {"handoff_id": "h", "execution_claim_token": "token", "execution_plan": []}
    writer = DurableHandoffModel(
        FunctionModel(lambda messages, info: original), store, "user", handoff
    )
    written = await writer.request([], None, ModelRequestParameters())
    unexpected_provider = AsyncMock(side_effect=AssertionError("Replay must not call provider"))
    reader = DurableHandoffModel(
        FunctionModel(unexpected_provider),
        store,
        "user",
        {**handoff, "execution_plan": writer.plan},
    )
    replayed = await reader.request([], None, ModelRequestParameters())
    retained = ModelMessagesTypeAdapter.dump_python([written], mode="json")[0]
    restored = ModelMessagesTypeAdapter.dump_python([replayed], mode="json")[0]
    retained.pop("usage")
    restored.pop("usage")
    assert restored == retained
    assert replayed.usage.input_tokens == replayed.usage.output_tokens == 0
    unexpected_provider.assert_not_awaited()
    assert replayed.parts[1].provider_details == {"thought_signature": "c2lnbmF0dXJl"}
    assert replayed.provider_name == "google"


async def test_durable_model_rejects_nonempty_thought_before_persisting_plan():
    from pydantic_ai.messages import ThinkingPart
    from pydantic_ai.models import ModelRequestParameters

    from src.tools.handoff_execution import DurableHandoffModel

    original = ModelResponse(parts=[ThinkingPart("hidden private reasoning sentinel")])
    store = SimpleNamespace(save_handoff_execution_plan=AsyncMock(return_value=True))
    model = DurableHandoffModel(
        FunctionModel(lambda messages, info: original),
        store,
        "user",
        {"handoff_id": "h", "execution_claim_token": "token", "execution_plan": []},
    )
    with pytest.raises(ValueError) as error:
        await model.request([], None, ModelRequestParameters())
    store.save_handoff_execution_plan.assert_not_awaited()
    assert "hidden private reasoning sentinel" not in str(error.value)


async def test_replayed_cancellation_preserves_new_reminder_created_after_crash(env, monkeypatch):
    row, confirm, _ = await propose(env)
    task = await env.store.create_task(env.user["user_id"], "fictional milk")
    original_reminder = await env.store.create_reminder(
        task["task_id"],
        env.user["user_id"],
        (env.clock.now + timedelta(minutes=20)).isoformat(),
    )
    env.script.tool("cancel_reminders", {"task_id": task["task_id"]})
    original = env.store.cancel_reminder_command

    async def commit_then_crash(*args, **kwargs):
        await original(*args, **kwargs)
        raise asyncio.CancelledError

    monkeypatch.setattr(env.store, "cancel_reminder_command", commit_then_crash)
    with pytest.raises(asyncio.CancelledError):
        await env.callback(confirm)
    assert original_reminder["status"] == "cancelled"
    newer = await env.store.create_reminder(
        task["task_id"],
        env.user["user_id"],
        (env.clock.now + timedelta(minutes=40)).isoformat(),
    )
    assert newer["status"] == "pending"
    monkeypatch.setattr(env.store, "cancel_reminder_command", original)
    env.clock.now += timedelta(minutes=6)
    env.script.text("The original Reminder was cancelled.")
    async with env.runtime.override(model=FunctionModel(env.script.respond)):
        await env.handlers.handoffs.recover()
    assert row["executed_at"] is not None
    assert original_reminder["status"] == "cancelled"
    assert newer["status"] == "pending"
    assert len(env.store.reminders) == 2
    assert len([key for key in env.store.command_receipts if ":cancel-reminder:" in key[1]]) == 1


@pytest.mark.parametrize("change_while_waiting", [None, "recipient", "activation"])
async def test_scheduler_recovery_shares_webhook_turn_lock_and_rechecks_current_endpoint(
    env,
    monkeypatch,
    change_while_waiting,
):
    from src import main
    from src.bot.update_claims import ChannelUpdateCoordinator

    coordinator = ChannelUpdateCoordinator(env.store)
    execute = AsyncMock()
    monkeypatch.setattr(main, "store", env.store)
    monkeypatch.setattr(main, "channel", env.channel)
    monkeypatch.setattr(main, "update_coordinator", coordinator)
    monkeypatch.setattr(env.handlers.handoffs, "execute", execute)
    monkeypatch.setattr(main, "handlers", env.handlers)
    monkeypatch.setattr(main, "handlers_by_channel", {env.channel.channel_id: env.handlers})
    started, release, scanned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pending = {"user_id": env.user["user_id"], "handoff_id": "fixture-pending"}

    async def list_pending():
        scanned.set()
        return [pending]

    async def live_turn():
        started.set()
        await release.wait()

    monkeypatch.setattr(env.store, "list_pending_handoff_executions", list_pending)
    webhook = asyncio.create_task(
        coordinator.run(
            update_id=991,
            chat_id=41001,
            update_kind="message",
            process=live_turn,
        )
    )
    await started.wait()
    recovery = asyncio.create_task(main._recover_pending_handoffs())
    await scanned.wait()
    execute.assert_not_awaited()
    if change_while_waiting == "recipient":
        await env.store.update_user(env.user["user_id"], {"telegram_chat_id": 41099})
    elif change_while_waiting == "activation":
        monkeypatch.setattr(
            env.store, "get_activation_state", AsyncMock(return_value={"completed": False})
        )
    release.set()
    await asyncio.gather(webhook, recovery)
    if change_while_waiting is None:
        execute.assert_awaited_once_with(
            await env.store.get_user_by_id(env.user["user_id"]), pending
        )
    else:
        execute.assert_not_awaited()


async def test_unchanged_mode_never_writes_active_selector(env, monkeypatch):
    setter = AsyncMock(wraps=env.store.set_active_mode)
    monkeypatch.setattr(env.store, "set_active_mode", setter)
    daily = await env.enter("daily")
    setter.assert_not_awaited()
    env.script.text()
    await env.send("Ordinary Daily", daily)
    setter.assert_not_awaited()
    coach = await env.enter("coach")
    assert setter.await_count >= 1
    setter.reset_mock()
    await env.enter("coach")
    env.script.text()
    await env.send("Ordinary Coach", coach)
    setter.assert_not_awaited()
    await env.store.revoke_mode_grant(env.user["user_id"], "coach", "owner", "test")
    await env.send("Revoked Coach", coach)
    assert "isn't available" in env.channel.last_text
