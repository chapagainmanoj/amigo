"""The disposable CLI fixture reaches the same gated Turn path as an activated account."""

from unittest.mock import patch

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from src.agent.catalogue import build_registry
from src.agent.runtime import ModeRuntime
from src.bot.handlers import BotHandlers
from src.cli import DEV_CHAT_ID, _seed_dev_user
from src.config import Settings
from src.memory.memory_store import InMemoryStore
from src.memory.sessions import SessionManager
from tests.fakes import FakeChannel, FakeScheduler


async def test_seeded_cli_user_passes_activation_and_runs_turn_without_pending_test_reminder():
    store = InMemoryStore()
    user = await _seed_dev_user(store)
    assert (await store.get_activation_state(user["supabase_auth_id"]))["completed"] is True
    assert await store.get_pending_reminders(user["user_id"]) == []
    assert await store.claim_scheduler_effects(25, "cli-fixture-check") == []
    channel = FakeChannel(channel_id="cli")
    runtime = ModeRuntime(build_registry())
    handlers = BotHandlers(
        channel, store, SessionManager(store), FakeScheduler(), mode_runtime=runtime
    )
    calls = []

    async def reply(messages, info):
        calls.append(1)
        return ModelResponse(parts=[TextPart("Fictional CLI reply")])

    with patch("src.config.settings", Settings(_env_file=None, access_mode="open")):
        async with runtime.override(model=FunctionModel(reply)):
            await handlers.handle_message(DEV_CHAT_ID, "Hello from a fictional CLI fixture")
    assert calls == [1]
    assert channel.last_text == "Fictional CLI reply"
