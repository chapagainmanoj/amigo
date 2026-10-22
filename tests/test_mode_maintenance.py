"""Maintenance keeps later stages/participants alive and preserves cancellation."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.channels.base import endpoint_dict
from src.conversations import ModeConversationService
from src.maintenance import run_isolated_steps
from tests.fakes import FakeChannel, FakeStore


async def test_isolated_stages_do_not_log_private_errors_and_cancellation_propagates(caplog):
    good = AsyncMock()
    await run_isolated_steps(
        [
            ("bad", AsyncMock(side_effect=ValueError("private provider payload"))),
            ("good", good),
        ]
    )
    good.assert_awaited_once()
    assert "error_type=ValueError" in caplog.text
    assert "private provider payload" not in caplog.text
    after = AsyncMock()
    with pytest.raises(asyncio.CancelledError):
        await run_isolated_steps(
            [
                ("cancel", AsyncMock(side_effect=asyncio.CancelledError())),
                ("after", after),
            ]
        )
    after.assert_not_awaited()


async def test_failed_provider_close_still_closes_store_and_continues_other_rows():
    store, channel = FakeStore(), FakeChannel(threads=True)
    service = ModeConversationService(store, channel)
    users = [await store.create_user(chat_id) for chat_id in (8812401, 8812402)]
    for user in users:
        ref = await channel.create_conversation(user["telegram_chat_id"], "Coach")
        await store.save_mode_conversation(
            user["user_id"], "coach", channel.channel_id, endpoint_dict(ref)
        )
    channel.close_conversation = AsyncMock(side_effect=[RuntimeError("provider failure"), None])
    await service.close_expired()  # Coach remains Planned and must close.
    assert channel.close_conversation.await_count == 2
    for user in users:
        rows = await store.list_mode_conversations()
        row = next(row for row in rows if row["user_id"] == user["user_id"])
        assert row["closed_at"] is not None


async def test_failed_grant_lookup_does_not_close_valid_row_or_block_later_participant():
    store, channel = FakeStore(), FakeChannel(threads=True)
    service = ModeConversationService(store, channel)
    users = [await store.create_user(chat_id) for chat_id in (8812403, 8812404)]
    for user in users:
        ref = await channel.create_conversation(user["telegram_chat_id"], "Coach")
        await store.save_mode_conversation(
            user["user_id"], "coach", channel.channel_id, endpoint_dict(ref)
        )
    store.get_active_mode_grant = AsyncMock(side_effect=[RuntimeError("DB failure"), None])
    await service.close_expired()
    rows = await store.list_mode_conversations()
    first = next(row for row in rows if row["user_id"] == users[0]["user_id"])
    second = next(row for row in rows if row["user_id"] == users[1]["user_id"])
    assert first["closed_at"] is None and second["closed_at"] is not None



async def test_main_maintenance_isolates_every_stage_and_resets_failed_readiness(monkeypatch):
    import src.main as main

    prune, close, recover = [AsyncMock(side_effect=RuntimeError("test")) for _ in range(3)]
    reconcile, drain = AsyncMock(), AsyncMock()
    worker = SimpleNamespace(admission_enabled=True, reconcile=reconcile, drain_once=drain)
    monkeypatch.setattr(
        main,
        "handlers",
        SimpleNamespace(
            memory=SimpleNamespace(service=SimpleNamespace(prune=prune)),
            turn_processor=SimpleNamespace(
                modes=SimpleNamespace(
                    conversations=SimpleNamespace(
                        close_expired=close,
                    )
                )
            ),
        ),
    )
    monkeypatch.setattr(main, "_recover_pending_handoffs", recover)
    monkeypatch.setattr(main, "coaching_worker", worker)
    monkeypatch.setattr(
        main,
        "coach_readiness",
        SimpleNamespace(
            complete=AsyncMock(side_effect=RuntimeError("readiness unavailable")),
        ),
    )
    await main._maintain_modes()
    for method in (prune, close, recover, reconcile, drain):
        method.assert_awaited_once()
    assert worker.admission_enabled is False


async def test_handoff_recovery_isolates_participant_read_failure(monkeypatch):
    import src.main as main

    execute = AsyncMock()
    user = {"user_id": "second", "supabase_auth_id": "auth"}
    monkeypatch.setattr(
        main,
        "store",
        SimpleNamespace(
            list_pending_handoff_executions=AsyncMock(
                return_value=[
                    {"user_id": "first"},
                    {"user_id": "second"},
                ]
            ),
            get_user_by_id=AsyncMock(side_effect=[RuntimeError("DB"), user, user]),
            get_activation_state=AsyncMock(return_value={"completed": True}),
        ),
    )
    monkeypatch.setattr(main, "channel", SimpleNamespace(recipient_for=AsyncMock(return_value=42)))

    @asynccontextmanager
    async def hold(_recipient):
        yield

    monkeypatch.setattr(
        main,
        "update_coordinator",
        SimpleNamespace(
            serializer=SimpleNamespace(
                hold=hold,
            )
        ),
    )
    monkeypatch.setattr(
        main, "handlers", SimpleNamespace(handoffs=SimpleNamespace(execute=execute))
    )
    await main._recover_pending_handoffs()
    execute.assert_awaited_once_with(user, {"user_id": "second"})
