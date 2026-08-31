"""Agent tool-calling tests (ADR 0002).

Uses pydantic-ai's TestModel which calls all available tools by default,
making it easy to verify tool behavior without a real LLM.
"""

from datetime import timedelta

from pydantic_ai.models.test import TestModel

from src.agent.agent import AgentDeps, amigo_agent, handle_message
from src.commands.base import CommandContext
from src.utils import now_in_tz
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


def _future_hhmm(timezone: str) -> str:
    local_target = now_in_tz(timezone) + timedelta(minutes=10)
    return local_target.strftime("%H:%M")


def _make_deps(store, scheduler, channel, user, session_id="session-1"):
    return AgentDeps(
        store=store,
        scheduler=scheduler,
        channel=channel,
        user=user,
        session_id=session_id,
        chat_id=123,
        timezone="Asia/Kathmandu",
        turn_id="test-turn",
    )


async def test_handle_message_stores_user_and_assistant_messages():
    """handle_message should store the user message and agent response."""
    store = FakeStore()
    scheduler = FakeScheduler()
    channel = FakeChannel()
    user = await store.create_user(123)
    await store.update_user(user["user_id"], {
        "name": "Dev", "timezone": "Asia/Kathmandu",
        "onboarding_complete": True, "onboarding_step": 3,
    })
    user = await store.get_user_by_chat_id(123)
    session = await store.create_session(user["user_id"])

    deps = _make_deps(store, scheduler, channel, user, session["session_id"])

    with amigo_agent.override(model=TestModel()):
        response = await handle_message(deps, "hello")

    assert isinstance(response, str)
    assert len(response) > 0

    # Should have at least 2 messages: user + assistant
    session_msgs = await store.get_session_messages(session["session_id"])
    roles = [m["role"] for m in session_msgs]
    assert "user" in roles
    assert "assistant" in roles


async def test_handle_message_returns_error_on_failure():
    """handle_message should return a friendly error when the agent fails."""
    store = FakeStore()
    channel = FakeChannel()
    scheduler = FakeScheduler()
    user = await store.create_user(123)
    await store.update_user(user["user_id"], {
        "name": "Dev", "timezone": "Asia/Kathmandu",
        "onboarding_complete": True, "onboarding_step": 3,
    })
    user = await store.get_user_by_chat_id(123)
    session = await store.create_session(user["user_id"])

    deps = _make_deps(store, scheduler, channel, user, session["session_id"])

    # Use a model that will raise
    class FailingModel(TestModel):
        async def request(self, *args, **kwargs):
            raise RuntimeError("LLM down")

    with amigo_agent.override(model=FailingModel()):
        response = await handle_message(deps, "hello")

    assert "trouble" in response.lower() or "sorry" in response.lower()


async def test_create_task_tool_creates_task_in_store():
    """Calling create_task tool directly should persist a task."""
    store = FakeStore()
    user = await store.create_user(123)
    await store.update_user(user["user_id"], {
        "name": "Dev", "timezone": "Asia/Kathmandu",
        "onboarding_complete": True, "onboarding_step": 3,
    })
    user = await store.get_user_by_chat_id(123)
    session = await store.create_session(user["user_id"])

    from src.tools.tasks import CreateTaskTool
    tool = CreateTaskTool(store)
    result = await tool.run(
        context=CommandContext(
            actor_user_id=user["user_id"],
            surface="telegram",
            idempotency_key="test:agent-create-task",
        ),
        title="Call mom",
        category="social",
        session_id=session["session_id"],
    )

    assert result["task"]["title"] == "Call mom"
    assert len(store.tasks) == 1


async def test_update_task_status_tool_marks_done_and_cancels_reminders():
    """update_task_status should update the task and cancel pending reminders."""
    store = FakeStore()
    user = await store.create_user(123)
    task = await store.create_task(user["user_id"], "finish slides")
    await store.create_reminder(task["task_id"], user["user_id"], "2099-01-01T00:00:00")

    from src.tools.tasks import UpdateTaskStatusTool
    tool = UpdateTaskStatusTool(store)

    result = await tool.run(
        context=CommandContext(user["user_id"], "telegram", "resolve-agent-test"),
        task_id=task["task_id"],
        status="completed",
    )

    assert result["task"]["status"] == "completed"
    assert result["effect_state"] == "queued"
    assert len(store.scheduler_outbox) == 1
