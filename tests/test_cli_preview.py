"""Development-only CLI preview of Planned Modes; the release catalogue stays unchanged."""

from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from src.agent.catalogue import build_registry
from src.bot.handlers import BotHandlers
from src.cli import DEV_CHAT_ID, _grant_preview_modes, _preview_runtime, _seed_dev_user
from src.config import Settings
from src.memory.memory_store import InMemoryStore
from src.memory.sessions import SessionManager
from tests.fakes import FakeChannel, FakeScheduler


def test_preview_refuses_production():
    with (
        patch("src.cli.settings", Settings(_env_file=None, app_env="production")),
        pytest.raises(SystemExit),
    ):
        _preview_runtime()


async def test_preview_lists_and_runs_planned_modes_without_changing_catalogue():
    with patch("src.cli.settings", Settings(_env_file=None)):
        runtime = _preview_runtime()
    assert {mode.id for mode in await build_registry().live()} == {"daily"}
    assert {mode.id for mode in await runtime.registry.live()} == {
        "daily", "coach", "reflect", "recommender",
    }
    store = InMemoryStore()
    await _seed_dev_user(store)
    # Coach is open to every activated participant; the rest need full access or a grant.
    assert set(await _grant_preview_modes(store, runtime)) == {"reflect", "recommender"}
    channel = FakeChannel()
    handlers = BotHandlers(
        channel, store, SessionManager(store), FakeScheduler(), mode_runtime=runtime
    )

    async def reply(messages, info):
        return ModelResponse(parts=[TextPart("Fictional preview reply")])

    with patch("src.config.settings", Settings(_env_file=None, access_mode="open")):
        await handlers.handle_message(DEV_CHAT_ID, "/mode")
        assert "/mode coach" in channel.last_text
        assert "/mode recommender" in channel.last_text
        async with runtime.override(model=FunctionModel(reply)):
            await handlers.handle_message(DEV_CHAT_ID, "/mode recommender")
            await handlers.handle_message(DEV_CHAT_ID, "Fictional laundry question")
    assert channel.last_text == "Fictional preview reply"
