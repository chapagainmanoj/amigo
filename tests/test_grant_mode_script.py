"""Operator access stays in Store policy; only successful grants create conversations."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts.grant_mode import apply_mode_access
from src.utils import utc_now
from tests.fakes import FakeChannel, FakeStore


@pytest.fixture
async def operator_setup(monkeypatch):
    from src import conversations

    store, channel = FakeStore(), FakeChannel(threads=True)
    users = [await store.create_user(800 + index) for index in range(6)]
    service = SimpleNamespace(ensure=AsyncMock(), close_expired=AsyncMock())
    monkeypatch.setattr(conversations, "ModeConversationService", lambda *args: service)
    registry = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(status="live")))
    return store, channel, users, service, registry


async def test_grants_observe_five_participant_cap_and_fourteen_day_default(operator_setup):
    store, channel, users, service, registry = operator_setup
    results = [await apply_mode_access(
        store, channel, user, "coach", "owner", "Internal trial", registry=registry,
    ) for user in users]
    assert [result["status"] for result in results] == ["granted"] * 5 + ["cap_reached"]
    assert service.ensure.await_count == 5
    grant = results[0]["grant"]
    from datetime import datetime
    duration = datetime.fromisoformat(grant["expires_at"]) - datetime.fromisoformat(
        grant["granted_at"]
    )
    assert timedelta(days=14) - timedelta(seconds=1) < duration <= timedelta(days=14)


async def test_revoke_closes_expired_conversations(operator_setup):
    store, channel, users, service, registry = operator_setup
    await store.grant_mode(users[0]["user_id"], "coach", "owner", "Internal trial")
    result = await apply_mode_access(
        store, channel, users[0], "coach", "owner", "End trial", revoke=True, registry=registry,
    )
    assert result["status"] == "revoked"
    service.close_expired.assert_awaited_once()
    service.ensure.assert_not_awaited()


@pytest.mark.parametrize("operator,reason", [(" ", "Trial"), ("owner", " ")])
async def test_reason_and_operator_required(operator_setup, operator, reason):
    store, channel, users, service, registry = operator_setup
    with pytest.raises(ValueError):
        await apply_mode_access(
            store, channel, users[0], "coach", operator, reason, registry=registry,
        )
    assert store._mode_state.grants == {}
    service.ensure.assert_not_awaited()


async def test_invalid_expiry_creates_no_conversation(operator_setup):
    store, channel, users, service, registry = operator_setup
    result = await apply_mode_access(
        store, channel, users[0], "coach", "owner", "Trial", registry=registry,
        expires_at=utc_now() + timedelta(days=15),
    )
    assert result["status"] == "invalid"
    service.ensure.assert_not_awaited()


async def test_planned_mode_cannot_be_granted(operator_setup):
    store, channel, users, service, registry = operator_setup
    registry.get.return_value = SimpleNamespace(status="planned")
    with pytest.raises(ValueError, match="must be live"):
        await apply_mode_access(
            store, channel, users[0], "coach", "owner", "Trial", registry=registry,
        )
    assert store._mode_state.grants == {}
