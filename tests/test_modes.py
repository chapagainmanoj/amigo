"""Modular Mode foundation, proven at two seams.

Seam 1 drives a Telegram message through the bot handlers with a scripted model and asserts only
what a participant or the model can observe. Seam 2 pins Daily's Tool schema and rendered
instructions, which were verified identical to the pre-refactor single agent when this landed.
"""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from pydantic_ai.messages import (
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel

from src.agent.catalogue import DAILY, build_registry
from src.agent.modes import ModeDefinition, ModeUnavailableError
from src.agent.policies import ExplicitThenDefault
from src.agent.registry import ModeRegistry
from src.agent.runtime import FAILURE_REPLY, ModeRuntime, default_runtime
from src.agent.safety import SAFETY_CORE
from src.bot.handlers import BotHandlers
from src.evaluation.gate_a import canonical_hash, tool_schema
from src.memory.sessions import SessionManager
from src.tools.context import ToolContext
from src.turns import SessionTurnOrchestrator
from src.utils import Clock, local_day_utc_range, yesterday_in_tz
from tests.fakes import FakeChannel, FakeScheduler, FakeStore

GOLDEN = Path(__file__).parent / "golden" / "daily_instructions.txt"
PROFILE_TZ = "Pacific/Kiritimati"  # UTC+14
TURN_TZ = "Etc/GMT+12"  # UTC-12
# Gate A's Daily Tool schema before Modes existed. A deliberate Tool change updates this on purpose.
DAILY_TOOL_SCHEMA_SHA256 = "0021a942df260e3fdb17b0ab6ee8d0dae09c1697349a99c5396ea7dcdb165013"
# The order the single pre-Mode agent presented its Tools in. Models are sensitive to order.
DAILY_TOOLS = [
    "create_task",
    "update_task_status",
    "schedule_reminder",
    "apply_later",
    "move_task_planning_day",
    "cancel_reminders",
]


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text)


class _Script:
    """A scripted model that records what it was offered on every request."""

    def __init__(self, *responses: ModelResponse):
        self.responses = list(responses)
        self.requests: list[dict] = []

    def respond(self, messages, info):
        self.requests.append(
            {
                "instructions": messages[-1].instructions or "",
                "tools": [tool.name for tool in info.function_tools],
                "conversation": [
                    (type(part).__name__, part.content)
                    for message in messages
                    for part in getattr(message, "parts", [])
                    if isinstance(part, UserPromptPart | TextPart)
                ],
                "retries": [
                    part
                    for message in messages
                    for part in getattr(message, "parts", [])
                    if isinstance(part, RetryPromptPart)
                ],
            }
        )
        return self.responses.pop(0) if self.responses else ModelResponse(parts=[TextPart("ok")])


async def _participant(store: FakeStore, chat_id: int) -> dict:
    user = await store.create_user(chat_id)
    await store.update_user(
        user["user_id"],
        {
            "name": "Asha",
            "timezone": "Asia/Kathmandu",
            "onboarding_complete": True,
            "onboarding_step": 3,
            "supabase_auth_id": f"auth-{chat_id}",
        },
    )
    return await store.get_user_by_chat_id(chat_id)


async def _send(
    store: FakeStore,
    text: str,
    script: _Script,
    *,
    chat_id: int = 900,
    runtime: ModeRuntime | None = None,
) -> FakeChannel:
    """Seam 1: one Telegram message through the real bot handlers."""
    channel = FakeChannel()
    handlers = BotHandlers(
        channel, store, SessionManager(store), FakeScheduler(), mode_runtime=runtime
    )
    async with (runtime or default_runtime).override(model=FunctionModel(script.respond)):
        with (
            patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True),
            patch.object(store, "get_activation_state", return_value={"completed": True}),
        ):
            await handlers.handle_message(chat_id, text, update_id=1)
    return channel


async def _deliver(store: FakeStore, text: str, chat_id: int, runtime: ModeRuntime) -> FakeChannel:
    """Seam 1 without installing a model override, for tests that manage it themselves."""
    channel = FakeChannel()
    handlers = BotHandlers(
        channel, store, SessionManager(store), FakeScheduler(), mode_runtime=runtime
    )
    with (
        patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True),
        patch.object(store, "get_activation_state", return_value={"completed": True}),
    ):
        await handlers.handle_message(chat_id, text, update_id=len(store.messages) + 1)
    return channel


def _journal(**overrides) -> ModeDefinition:
    """A live test Mode with no Tools and instructions that never mention safety."""
    fields = {
        "id": "journal",
        "name": "Journal",
        "purpose": "Help me write down my day.",
        "status": "live",
        "instructions": lambda facts: f"You help {facts.participant_name} write a journal entry.",
        "eval_suite": "evals/gate_a/v1/cases.json",
    }
    return ModeDefinition(**{**fields, **overrides})


def _runtime_for(mode: ModeDefinition, **kwargs) -> ModeRuntime:
    return ModeRuntime(
        ModeRegistry((DAILY, mode)), routing=ExplicitThenDefault(default=mode.id), **kwargs
    )


def _nothing_written(store: FakeStore) -> bool:
    return not (
        store.messages
        or store.tasks
        or store.reminders
        or store.scheduler_outbox
        or store.command_receipts
    )


# ── Seam 1: the Turn ──


async def test_daily_is_offered_exactly_its_tools_and_the_whole_safety_core():
    store = FakeStore()
    await _participant(store, 900)
    script = _Script()

    channel = await _send(store, "hello", script)

    assert channel.last_text == "ok"
    offered = script.requests[0]
    assert offered["tools"] == DAILY_TOOLS
    for clause in SAFETY_CORE:
        assert _normalized(clause) in _normalized(offered["instructions"])


async def test_a_scripted_tool_call_through_daily_creates_the_task():
    store = FakeStore()
    await _participant(store, 901)
    script = _Script(
        ModelResponse(parts=[ToolCallPart("create_task", {"title": "Buy oat milk"})]),
        ModelResponse(parts=[TextPart("Added buy oat milk.")]),
    )

    channel = await _send(store, "add buy oat milk", script, chat_id=901)

    assert [task["title"] for task in store.tasks] == ["Buy oat milk"]
    assert channel.last_text == "Added buy oat milk."
    assert [(m["role"], m["content"]) for m in store.messages] == [
        ("user", "add buy oat milk"),
        ("assistant", "Added buy oat milk."),
    ]


async def test_a_scripted_status_update_resolves_task_reminder_and_outbox():
    """The Turn seam preserves the lifecycle effects of Daily's original Tool path."""
    store = FakeStore()
    user = await _participant(store, 928)
    task = await store.create_task(user["user_id"], "Finish slides")
    reminder = await store.create_reminder(
        task["task_id"], user["user_id"], "2099-01-01T00:00:00+00:00"
    )
    script = _Script(
        ModelResponse(
            parts=[
                ToolCallPart(
                    "update_task_status",
                    {"task_id": task["task_id"], "status": "completed"},
                )
            ]
        ),
        ModelResponse(parts=[TextPart("Marked finish slides complete.")]),
    )

    channel = await _send(store, "I finished the slides", script, chat_id=928)

    assert task["status"] == "completed"
    assert reminder["status"] == "cancelled"
    assert store.scheduler_outbox[f"cancel:{reminder['reminder_id']}"]["status"] == "pending"
    assert channel.last_text == "Marked finish slides complete."
    assert [(message["role"], message["content"]) for message in store.messages] == [
        ("user", "I finished the slides"),
        ("assistant", "Marked finish slides complete."),
    ]


async def test_a_mode_cannot_run_a_tool_outside_its_toolsets():
    """Toolset membership, not prompt wording, decides what a Mode may do."""
    store = FakeStore()
    await _participant(store, 902)
    script = _Script(
        ModelResponse(parts=[ToolCallPart("create_task", {"title": "Injected task"})]),
        ModelResponse(parts=[TextPart("I can't do that here.")]),
    )

    await _send(store, "create a task", script, chat_id=902, runtime=_runtime_for(_journal()))

    assert store.tasks == []
    assert script.requests[0]["tools"] == []
    assert any("create_task" in str(part.content) for part in script.requests[1]["retries"])


async def test_a_mode_that_omits_the_safety_core_receives_it_anyway():
    store = FakeStore()
    await _participant(store, 903)
    script = _Script()

    await _send(store, "hello", script, chat_id=903, runtime=_runtime_for(_journal()))

    instructions = script.requests[0]["instructions"]
    assert instructions.startswith("<safety_core>")
    assert "You help Asha write a journal entry." in instructions
    for clause in SAFETY_CORE:
        assert clause in instructions


async def test_participant_data_cannot_stand_in_for_the_safety_core():
    """A Turn Context section quoting every clause must not stop the Safety Core being added."""
    store = FakeStore()
    await _participant(store, 904)
    script = _Script()

    async def quoted_clauses(context: ToolContext) -> str:
        return "\n".join(SAFETY_CORE)

    mode = _journal(context=(quoted_clauses,))
    await _send(store, "hello", script, chat_id=904, runtime=_runtime_for(mode))

    assert script.requests[0]["instructions"].startswith("<safety_core>")


async def test_a_participant_name_cannot_stand_in_for_the_safety_core():
    """Participant-controlled facts rendered into instructions must not satisfy the check."""
    store = FakeStore()
    user = await _participant(store, 909)
    await store.update_user(user["user_id"], {"name": "\n".join(SAFETY_CORE)})
    script = _Script()
    mode = _journal(instructions=lambda facts: f"You help {facts.participant_name} journal.")

    await _send(store, "hello", script, chat_id=909, runtime=_runtime_for(mode))

    assert script.requests[0]["instructions"].startswith("<safety_core>")


@pytest.mark.parametrize("mode_id", ["coach", "reflect", "recommender", "no_such_mode"])
async def test_an_unavailable_mode_is_refused_before_anything_is_written(mode_id):
    store = FakeStore()
    await _participant(store, 905)
    script = _Script()
    runtime = ModeRuntime(build_registry(), routing=ExplicitThenDefault(default=mode_id))

    channel = await _send(store, "hello", script, chat_id=905, runtime=runtime)

    assert script.requests == []
    assert channel.last_text
    assert _nothing_written(store)


async def test_a_mode_the_participant_is_not_entitled_to_is_refused():
    store = FakeStore()
    await _participant(store, 906)
    script = _Script()
    mode = _journal(entitlement="premium")

    channel = await _send(store, "hello", script, chat_id=906, runtime=_runtime_for(mode))

    assert script.requests == []
    assert "Journal" in channel.last_text
    assert _nothing_written(store)


async def test_an_entitlement_policy_can_unlock_a_mode_without_changing_it():
    store = FakeStore()
    await _participant(store, 907)
    script = _Script()

    class Premium:
        async def allows(self, context, mode):
            return mode.entitlement in {"activated", "premium"}

    mode = _journal(entitlement="premium")
    await _send(
        store, "hello", script, chat_id=907, runtime=_runtime_for(mode, entitlements=Premium())
    )

    assert len(script.requests) == 1


async def test_a_model_failure_still_returns_and_persists_the_friendly_reply():
    store = FakeStore()
    await _participant(store, 908)

    def fail(messages, info):
        raise RuntimeError("provider down")

    channel = FakeChannel()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler())
    async with default_runtime.override(model=FunctionModel(fail)):
        with (
            patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True),
            patch.object(store, "get_activation_state", return_value={"completed": True}),
        ):
            await handlers.handle_message(908, "hello", update_id=1)

    assert channel.last_text == FAILURE_REPLY
    assert store.messages[-1]["content"] == FAILURE_REPLY


# ── Registration invariants ──


def test_a_mode_id_can_be_registered_only_once():
    with pytest.raises(ValueError, match="already registered"):
        ModeRegistry((_journal(), _journal()))


def test_a_live_mode_must_declare_instructions():
    with pytest.raises(ValueError, match="must declare instructions"):
        _journal(instructions=None)


def test_mode_ids_are_stable_identifiers():
    with pytest.raises(ValueError, match="invalid Mode id"):
        _journal(id="Coach Mode")


def test_the_catalogue_registers_daily_live_and_the_rest_planned():
    statuses = {mode.id: mode.status for mode in build_registry()}
    assert statuses == {
        "daily": "live",
        "coach": "planned",
        "reflect": "planned",
        "recommender": "planned",
    }


async def test_registry_public_operations_follow_the_async_method_contract():
    registry = ModeRegistry()
    mode = _journal()

    await registry.register(mode)

    assert await registry.get("journal") is mode
    assert await registry.live() == [mode]


# ── Seam 2: Daily's contract snapshot ──


def test_daily_tool_schema_is_unchanged():
    assert canonical_hash(tool_schema()) == DAILY_TOOL_SCHEMA_SHA256


def test_gate_a_tool_schema_resolves_daily_through_the_registry():
    registry = ModeRegistry((_journal(id="daily"),))

    with patch("src.agent.catalogue.build_registry", return_value=registry):
        assert tool_schema() == []


class _FixedClock(Clock):
    def utc_now(self) -> datetime:
        return datetime(2026, 9, 1, 4, 15)

    def now_in_tz(self, timezone: str) -> datetime:
        return datetime(2026, 9, 1, 4, 15, tzinfo=UTC).astimezone(ZoneInfo(timezone))


async def render_daily_instructions() -> str:
    """Daily's first-Turn instructions for a rich fixed Turn Context, ids made positional.

    Every section is populated, a completed Task and an Inbox Task are present, and the Tool
    Context timezone differs from the profile timezone, so each of those behaviours is pinned.
    """
    store = FakeStore()
    user = await _participant(store, 777)
    # The profile and the Tool Context use timezones 26 hours apart, so their calendar dates never
    # coincide and the golden shows which one each Turn Context section reads, at any hour.
    await store.update_user(user["user_id"], {"timezone": PROFILE_TZ})
    user = await store.get_user_by_chat_id(777)
    yesterday = await store.create_session(user["user_id"], "evening")
    start_utc, _ = local_day_utc_range(PROFILE_TZ, yesterday_in_tz(PROFILE_TZ))
    yesterday["started_at"] = (start_utc + timedelta(hours=12)).isoformat()
    yesterday["context_summary"] = "Planned the expense report."
    session = await store.create_session(user["user_id"], "casual")
    first = await store.create_task(user["user_id"], "Submit expense report", timezone=PROFILE_TZ)
    await store.create_task(user["user_id"], "Call Mom", timezone=PROFILE_TZ)
    completed = await store.create_task(user["user_id"], "Morning run", timezone=PROFILE_TZ)
    completed["status"] = "completed"
    inbox = await store.create_task(user["user_id"], "Renew passport", timezone=PROFILE_TZ)
    inbox["due_date"] = None
    await store.create_reminder(first["task_id"], user["user_id"], "2026-09-01T09:00:00+00:00")
    script = _Script()
    context = ToolContext(
        store=store,
        scheduler=FakeScheduler(),
        channel=FakeChannel(),
        user=user,
        session_id=session["session_id"],
        chat_id=777,
        timezone=TURN_TZ,
        turn_id="golden",
        clock=_FixedClock(),
    )
    await default_runtime.run_turn(context, "hi", model=FunctionModel(script.respond))
    seen: dict[str, str] = {}
    return re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        lambda match: seen.setdefault(match.group(0), f"<id{len(seen) + 1}>"),
        script.requests[0]["instructions"],
    )


async def test_daily_instructions_are_unchanged():
    assert await render_daily_instructions() == GOLDEN.read_text()


# ── Behaviour the first review showed was unpinned ──


async def test_a_disabled_mode_is_refused_before_anything_is_written():
    store = FakeStore()
    await _participant(store, 910)
    script = _Script()

    channel = await _send(
        store, "hello", script, chat_id=910, runtime=_runtime_for(_journal(status="disabled"))
    )

    assert script.requests == []
    assert "Journal" in channel.last_text
    assert _nothing_written(store)


async def test_session_history_reaches_the_model_once_and_in_role():
    store = FakeStore()
    await _participant(store, 911)
    script = _Script(
        ModelResponse(parts=[TextPart("First reply.")]),
        ModelResponse(parts=[TextPart("Second reply.")]),
    )
    async with default_runtime.override(model=FunctionModel(script.respond)):
        await _deliver(store, "first message", 911, default_runtime)
        await _deliver(store, "second message", 911, default_runtime)

    assert script.requests[1]["conversation"] == [
        ("UserPromptPart", "first message"),
        ("TextPart", "First reply."),
        ("UserPromptPart", "second message"),
    ]
    assert script.requests[1]["instructions"], "the second Turn must still carry instructions"


async def test_an_inner_override_does_not_outlive_its_block():
    store = FakeStore()
    await _participant(store, 912)
    outer, inner = _Script(), _Script()
    runtime = ModeRuntime(build_registry())
    async with runtime.override(model=FunctionModel(outer.respond)):
        async with runtime.override(model=FunctionModel(inner.respond)):
            pass
        await _deliver(store, "hello", 912, runtime)

    assert len(outer.requests) == 1
    assert inner.requests == []


async def test_an_explicit_model_beats_an_active_override():
    """The Gate A runner passes its model explicitly; an override must never replace it."""
    store = FakeStore()
    user = await _participant(store, 913)
    session = await store.create_session(user["user_id"], "casual")
    overridden, explicit = _Script(), _Script()
    context = ToolContext(
        store=store,
        scheduler=FakeScheduler(),
        channel=FakeChannel(),
        user=user,
        session_id=session["session_id"],
        chat_id=913,
        timezone="Asia/Kathmandu",
        turn_id="explicit",
    )
    async with default_runtime.override(model=FunctionModel(overridden.respond)):
        await default_runtime.run_turn(context, "hi", model=FunctionModel(explicit.respond))

    assert len(explicit.requests) == 1
    assert overridden.requests == []


async def test_a_requested_mode_is_honoured_and_refused_when_unavailable():
    store = FakeStore()
    user = await _participant(store, 914)
    session = await store.create_session(user["user_id"], "casual")
    context = ToolContext(
        store=store,
        scheduler=FakeScheduler(),
        channel=FakeChannel(),
        user=user,
        session_id=session["session_id"],
        chat_id=914,
        timezone="Asia/Kathmandu",
        turn_id="requested",
    )
    script = _Script()
    async with default_runtime.override(model=FunctionModel(script.respond)):
        reply = await SessionTurnOrchestrator(default_runtime).handle_turn(
            context, "hi", requested_mode="coach"
        )

    assert reply == "Coach isn't available yet."
    assert script.requests == []
    assert store.messages == []


async def test_an_explicit_empty_mode_identifier_is_unknown_not_daily():
    store = FakeStore()
    context = await _direct_context(store, 929)
    script = _Script()

    async with default_runtime.override(model=FunctionModel(script.respond)):
        reply = await SessionTurnOrchestrator(default_runtime).handle_turn(
            context, "hi", requested_mode=""
        )

    assert reply == "That mode doesn't exist."
    assert script.requests == []
    assert _nothing_written(store)


async def test_stating_one_clause_is_not_stating_the_safety_core():
    store = FakeStore()
    await _participant(store, 915)
    script = _Script()
    mode = _journal(instructions=lambda facts: f"You help people journal. {SAFETY_CORE[0]}")

    await _send(store, "hello", script, chat_id=915, runtime=_runtime_for(mode))

    assert script.requests[0]["instructions"].startswith("<safety_core>")


async def test_a_mode_whose_real_facts_push_clauses_out_still_receives_the_safety_core():
    """Passing the placeholder check is not enough if the delivered text loses a clause."""
    store = FakeStore()
    user = await _participant(store, 916)
    await store.update_user(user["user_id"], {"name": "x" * 400})
    budget = len(" ".join(SAFETY_CORE)) + 40
    mode = _journal(
        instructions=lambda facts: (f"You help {facts.participant_name}. " + " ".join(SAFETY_CORE))[
            :budget
        ]
    )
    script = _Script()

    await _send(store, "hello", script, chat_id=916, runtime=_runtime_for(mode))

    delivered = _normalized(script.requests[0]["instructions"])
    for clause in SAFETY_CORE:
        assert _normalized(clause) in delivered


async def test_a_tool_argument_failure_gets_exactly_one_retry():
    store = FakeStore()
    await _participant(store, 917)
    script = _Script(
        *[ModelResponse(parts=[ToolCallPart("create_task", {"category": "work"})])] * 5
    )

    channel = await _send(store, "add something", script, chat_id=917)

    assert len(script.requests) == 2
    assert channel.last_text == FAILURE_REPLY
    assert store.tasks == []


async def test_an_empty_model_response_gets_exactly_one_retry():
    store = FakeStore()
    await _participant(store, 918)
    script = _Script(*[ModelResponse(parts=[])] * 5)

    channel = await _send(store, "hello", script, chat_id=918)

    assert len(script.requests) == 2
    assert channel.last_text == FAILURE_REPLY


async def test_a_failure_while_choosing_the_mode_writes_nothing():
    store = FakeStore()
    await _participant(store, 919)
    script = _Script()

    class Broken:
        async def allows(self, context, mode):
            raise RuntimeError("entitlement service down")

    channel = await _send(
        store,
        "hello",
        script,
        chat_id=919,
        runtime=ModeRuntime(build_registry(), entitlements=Broken()),
    )

    assert channel.last_text == FAILURE_REPLY
    assert script.requests == []
    assert _nothing_written(store)


async def test_each_turn_records_the_mode_that_handled_it(caplog):
    store = FakeStore()
    await _participant(store, 920)

    with caplog.at_level("INFO", logger="src.telemetry"):
        await _send(store, "hello", _Script(), chat_id=920)

    records = [record.turn_record for record in caplog.records if hasattr(record, "turn_record")]
    assert len(records) == 1
    assert records[0]["mode_id"] == "daily"


def test_a_live_mode_whose_instructions_cannot_render_fails_at_registration():
    def broken(facts):
        raise KeyError("missing template field")

    with pytest.raises(ValueError, match="failed to render"):
        ModeRegistry((_journal(instructions=broken),))


def test_a_tool_order_can_only_name_tools_the_mode_has():
    from src.tools.toolsets import TASKS

    with pytest.raises(ValueError, match="does not have"):
        ModeRegistry((_journal(toolsets=(TASKS,), tool_order=("create_task", "apply_later")),))


async def test_each_toolset_holds_its_own_domain():
    """Future Modes pick Toolsets by domain, so membership is a contract, not just Daily's order."""
    from src.tools.toolsets import REMINDERS, TASKS

    offered = {}
    for name, toolset in (("tasks", TASKS), ("reminders", REMINDERS)):
        store = FakeStore()
        await _participant(store, 921)
        script = _Script()
        mode = _journal(toolsets=(toolset,))
        await _send(store, "hello", script, chat_id=921, runtime=_runtime_for(mode))
        offered[name] = script.requests[0]["tools"]

    assert offered == {
        "tasks": ["create_task", "update_task_status", "move_task_planning_day"],
        "reminders": ["schedule_reminder", "apply_later", "cancel_reminders"],
    }


def test_a_tool_order_cannot_name_a_tool_twice():
    from src.tools.toolsets import TASKS

    with pytest.raises(ValueError, match="more than once"):
        ModeRegistry((_journal(toolsets=(TASKS,), tool_order=("create_task", "create_task")),))


# ── Behaviour the second review showed was unpinned ──


async def _direct_context(store: FakeStore, chat_id: int) -> ToolContext:
    user = await _participant(store, chat_id)
    session = await store.create_session(user["user_id"], "casual")
    return ToolContext(
        store=store,
        scheduler=FakeScheduler(),
        channel=FakeChannel(),
        user=user,
        session_id=session["session_id"],
        chat_id=chat_id,
        timezone="Asia/Kathmandu",
        turn_id="direct",
    )


@pytest.mark.parametrize("requested", ["coach", "journal"])
async def test_run_turn_refuses_before_writing_just_like_handle_turn(requested):
    """Gate A drives `run_turn` directly, so it must authorize exactly as the Turn loop does."""
    store = FakeStore()
    context = await _direct_context(store, 922)
    runtime = ModeRuntime(ModeRegistry((*build_registry(), _journal(entitlement="premium"))))
    script = _Script()

    with pytest.raises(ModeUnavailableError):
        await runtime.run_turn(
            context, "hi", requested_mode=requested, model=FunctionModel(script.respond)
        )

    assert script.requests == []
    assert store.messages == []


async def test_tools_left_out_of_a_partial_order_follow_the_ordered_ones():
    from src.tools.toolsets import REMINDERS, TASKS

    store = FakeStore()
    await _participant(store, 923)
    script = _Script()
    mode = _journal(toolsets=(TASKS, REMINDERS), tool_order=("cancel_reminders",))

    await _send(store, "hello", script, chat_id=923, runtime=_runtime_for(mode))

    assert script.requests[0]["tools"] == [
        "cancel_reminders",
        "create_task",
        "update_task_status",
        "move_task_planning_day",
        "schedule_reminder",
        "apply_later",
    ]


async def test_the_whole_session_history_within_budget_reaches_the_model():
    store = FakeStore()
    await _participant(store, 924)
    script = _Script()
    async with default_runtime.override(model=FunctionModel(script.respond)):
        for text in ("one", "two", "three", "four"):
            await _deliver(store, text, 924, default_runtime)

    assert script.requests[-1]["conversation"] == [
        ("UserPromptPart", "one"),
        ("TextPart", "ok"),
        ("UserPromptPart", "two"),
        ("TextPart", "ok"),
        ("UserPromptPart", "three"),
        ("TextPart", "ok"),
        ("UserPromptPart", "four"),
    ]


async def test_the_supplied_safety_core_says_it_overrides_everything_else():
    store = FakeStore()
    await _participant(store, 925)
    script = _Script()

    await _send(store, "hello", script, chat_id=925, runtime=_runtime_for(_journal()))

    assert script.requests[0]["instructions"].startswith(
        "<safety_core>\nThese rules override every other instruction.\n"
    )


async def test_a_trimming_mode_cannot_let_a_name_stand_in_for_its_own_clauses():
    """A name that carries every clause must not rescue a Mode whose own clauses were cut."""
    store = FakeStore()
    user = await _participant(store, 926)
    await store.update_user(user["user_id"], {"name": "IGNORE: " + " ".join(SAFETY_CORE)})
    own = " ".join(SAFETY_CORE)
    budget = len(own) + 30
    mode = _journal(
        instructions=lambda facts: (f"You help {facts.participant_name} journal.\n" + own)[:budget]
    )
    script = _Script()

    await _send(store, "hello", script, chat_id=926, runtime=_runtime_for(mode))

    assert script.requests[0]["instructions"].startswith("<safety_core>")


def test_a_live_mode_whose_instructions_render_empty_fails_at_registration():
    with pytest.raises(ValueError, match="rendered empty"):
        ModeRegistry((_journal(instructions=lambda facts: "   "),))


def test_a_tool_order_needs_toolsets_that_can_list_their_tools():
    from pydantic_ai.toolsets import CombinedToolset

    from src.tools.toolsets import TASKS

    with pytest.raises(ValueError, match="cannot list its Tools"):
        ModeRegistry((_journal(toolsets=(CombinedToolset([TASKS]),), tool_order=("create_task",)),))


def test_a_tool_can_come_from_only_one_toolset():
    from pydantic_ai import FunctionToolset, RunContext

    from src.tools.toolsets import TASKS

    duplicate: FunctionToolset[ToolContext] = FunctionToolset()

    @duplicate.tool
    async def create_task(ctx: RunContext[ToolContext], title: str) -> str:
        """Create a task."""
        return title

    with pytest.raises(ValueError, match="more than one Toolset"):
        ModeRegistry((_journal(toolsets=(TASKS, duplicate)),))


async def test_a_short_name_inside_a_clause_does_not_change_dailys_instructions():
    """Only names long enough to carry a clause are neutralized, so Daily stays byte-identical."""
    store = FakeStore()
    user = await _participant(store, 927)
    await store.update_user(user["user_id"], {"name": "Amigo"})
    script = _Script()

    await _send(store, "hello", script, chat_id=927)

    instructions = script.requests[0]["instructions"]
    assert not instructions.startswith("<safety_core>")
    assert instructions.startswith("You are Amigo")
