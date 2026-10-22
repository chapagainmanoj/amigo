"""A concurrent Memory settings change gives an owned deterministic recovery reply."""

from unittest.mock import AsyncMock

from src.bot.handlers import BotHandlers
from src.channels.base import ConversationRef
from src.commands.base import StaleVersionError
from src.config import Settings
from src.memory.sessions import SessionManager
from tests.fakes import FakeChannel, FakeScheduler, FakeStore
from tests.test_modes import _participant


async def test_memory_pause_stale_version_replies_in_place_without_model_or_private_error(
    monkeypatch,
):
    monkeypatch.setattr("src.config.settings", Settings(_env_file=None))
    store = FakeStore()
    await _participant(store, 921901)
    channel = FakeChannel(threads=True)
    handlers = BotHandlers(channel, store, SessionManager(store), FakeScheduler())
    handlers._is_allowed = AsyncMock(return_value=True)
    store.get_activation_state = AsyncMock(return_value={"completed": True})
    handlers.memory.handle = AsyncMock(side_effect=StaleVersionError("PRIVATE_STALE_SETTINGS"))
    handlers.turn_processor.handle = AsyncMock()
    ref = ConversationRef("telegram", {"chat_id": 921901, "thread_id": 19})
    await handlers.handle_message(921901, "/memory pause", conversation=ref)
    handlers.turn_processor.handle.assert_not_awaited()
    assert len(channel.sent) == 1
    assert channel.sent[0]["conversation"] == ref
    assert "Memory settings changed" in channel.sent[0]["text"]
    assert "PRIVATE" not in channel.sent[0]["text"]
