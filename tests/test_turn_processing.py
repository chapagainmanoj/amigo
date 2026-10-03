"""Turn processing integration tests."""

from unittest.mock import patch

from pydantic_ai.models.test import TestModel

from src.agent.runtime import default_runtime
from src.bot.handlers import BotHandlers
from src.memory.sessions import SessionManager
from tests.fakes import FakeChannel, FakeScheduler, FakeStore


async def test_onboarded_user_gets_agent_response():
    """An onboarded user's message should go through the agent and produce a response."""
    store = FakeStore()
    channel = FakeChannel()
    scheduler = FakeScheduler()
    handlers = BotHandlers(channel, store, SessionManager(store), scheduler)
    user = await store.create_user(123)
    await store.update_user(
        user["user_id"],
        {
            "name": "Dev",
            "timezone": "Asia/Kathmandu",
            "onboarding_complete": True,
            "onboarding_step": 3,
            "supabase_auth_id": "auth-turn-response",
        },
    )

    async with default_runtime.override(model=TestModel()):
        with (
            patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True),
            patch.object(store, "get_activation_state", return_value={"completed": True}),
        ):
            await handlers.handle_message(123, "hello amigo")

    # Should have sent a response
    assert len(channel.sent) >= 1
    assert len(channel.last_text) > 0


async def test_close_signal_closes_session():
    """A close signal like 'goodnight' should close the session."""
    store = FakeStore()
    channel = FakeChannel()
    scheduler = FakeScheduler()
    handlers = BotHandlers(channel, store, SessionManager(store), scheduler)
    user = await store.create_user(123)
    await store.update_user(
        user["user_id"],
        {
            "name": "Dev",
            "timezone": "Asia/Kathmandu",
            "onboarding_complete": True,
            "onboarding_step": 3,
            "supabase_auth_id": "auth-close-signal",
        },
    )

    with (
        patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True),
        patch.object(store, "get_activation_state", return_value={"completed": True}),
    ):
        await handlers.handle_message(123, "goodnight")

    assert "night" in channel.last_text.lower() or "🌙" in channel.last_text


async def test_telegram_update_id_becomes_stable_turn_id():
    store = FakeStore()
    channel = FakeChannel()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler())
    user = await store.create_user(123)
    await store.update_user(
        user["user_id"],
        {
            "timezone": "UTC",
            "onboarding_complete": True,
            "onboarding_step": 3,
            "supabase_auth_id": "auth-stable-turn",
        },
    )
    captured_turn_ids = []

    async def capture(context, _text):
        captured_turn_ids.append(context.turn_id)
        return "ok"

    with (
        patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True),
        patch.object(store, "get_activation_state", return_value={"completed": True}),
        patch.object(handlers.turn_processor.turn_orchestrator, "handle_turn", side_effect=capture),
    ):
        await handlers.handle_message(123, "make a task", update_id=987654)

    assert captured_turn_ids == ["987654"]


async def test_every_turn_in_a_session_receives_the_safety_instructions():
    """The rules must reach the model on the second message of a Session, not only the first.

    A system prompt is only injected when a run starts with empty history, and every later Turn
    in a Session starts with history, so the rules silently disappeared after the first message.
    """
    from pydantic_ai.messages import ModelResponse, SystemPromptPart, TextPart
    from pydantic_ai.models.function import FunctionModel

    store = FakeStore()
    channel = FakeChannel()
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler())
    user = await store.create_user(321)
    await store.update_user(
        user["user_id"],
        {
            "name": "Dev",
            "timezone": "Asia/Kathmandu",
            "onboarding_complete": True,
            "onboarding_step": 3,
            "supabase_auth_id": "auth-every-turn",
        },
    )
    delivered = []

    def respond(messages, info):
        request = messages[-1]
        system_parts = [
            part.content
            for message in messages
            for part in getattr(message, "parts", [])
            if isinstance(part, SystemPromptPart)
        ]
        delivered.append("\n".join([request.instructions or "", *system_parts]))
        return ModelResponse(parts=[TextPart("ok")])

    async with default_runtime.override(model=FunctionModel(respond)):
        with (
            patch("src.bot.handlers.BotHandlers._is_allowed", return_value=True),
            patch.object(store, "get_activation_state", return_value={"completed": True}),
        ):
            await handlers.handle_message(321, "hello", update_id=1)
            await handlers.handle_message(321, "I feel like hurting myself", update_id=2)

    assert len(delivered) == 2
    for turn, text in enumerate(delivered, start=1):
        assert "non-clinical" in text, f"turn {turn} reached the model without the rules"
        assert "imminent self-harm" in text, f"turn {turn} lost the Crisis Referral rule"
