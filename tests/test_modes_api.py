"""Authenticated Mode availability exposes only the participant's grant metadata."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI

from src.api.dependencies import get_activated_user, get_store
from src.api.modes import router
from src.config import settings


async def test_mode_endpoint_uses_owned_grants_and_channel_links(monkeypatch):
    from src.api import modes

    definitions = [
        SimpleNamespace(
            id="daily",
            name="Daily",
            purpose="Today",
            status="live",
            entitlement="activated",
            entry_guard=None,
        ),
        SimpleNamespace(
            id="coach",
            name="Coach",
            purpose="One goal",
            status="live",
            entitlement="grant",
            entry_guard=None,
        ),
        SimpleNamespace(
            id="reflect",
            name="Reflect",
            purpose="Reflect",
            status="planned",
            entitlement="grant",
            entry_guard=None,
        ),
    ]
    monkeypatch.setattr(modes, "build_registry", lambda: definitions)
    expiry = "2026-11-01T12:00:00+00:00"
    store = SimpleNamespace(
        count_participant_messages=AsyncMock(return_value=0),
        get_active_session=AsyncMock(return_value=None),
        list_mode_conversations=AsyncMock(
            return_value=[
                {
                    "user_id": "owner",
                    "mode_id": "coach",
                    "channel": "fake",
                    "endpoint": {"address": "opaque"},
                    "closed_at": None,
                }
            ]
        ),
        get_active_mode_grant=AsyncMock(
            side_effect=lambda user, mode: {"expires_at": expiry} if mode == "coach" else None
        ),
    )
    channel = SimpleNamespace(
        channel_id="fake",
        conversation_link=AsyncMock(return_value="https://example.test/chat"),
    )
    app = FastAPI()
    app.include_router(router)
    app.state.channel = channel
    app.dependency_overrides[get_activated_user] = lambda: {"user_id": "owner"}
    app.dependency_overrides[get_store] = lambda: store
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/modes?user_id=another-participant")
    assert response.status_code == 200
    result = response.json()["modes"]
    assert [row["available"] for row in result] == [True, True, False]
    assert result[1]["grant_expires_at"] == expiry
    assert result[2]["deep_link"] is None
    assert "endpoint" not in str(response.json()) and "opaque" not in str(response.json())
    store.list_mode_conversations.assert_awaited_once_with("owner")
    assert all(call.args[0] == "owner" for call in store.get_active_mode_grant.call_args_list)
    assert channel.conversation_link.call_args_list[0].args == (None,)
    assert channel.conversation_link.call_args_list[1].args[0].endpoint["address"] == "opaque"


async def test_modes_endpoint_requires_authentication():
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/modes")
    assert response.status_code == 401


async def test_missing_grant_denies_live_mode_link(monkeypatch):
    from src.api import modes

    monkeypatch.setattr(
        modes,
        "build_registry",
        lambda: [
            SimpleNamespace(
                id="coach",
                name="Coach",
                purpose="One goal",
                status="live",
                entitlement="grant",
                entry_guard=None,
            )
        ],
    )
    store = SimpleNamespace(
        count_participant_messages=AsyncMock(return_value=0),
        get_active_session=AsyncMock(return_value=None),
        list_mode_conversations=AsyncMock(return_value=[]),
        get_active_mode_grant=AsyncMock(return_value=None),
    )
    channel = SimpleNamespace(channel_id="fake", conversation_link=AsyncMock())
    app = FastAPI()
    app.include_router(router)
    app.state.channel = channel
    app.dependency_overrides[get_activated_user] = lambda: {"user_id": "owner"}
    app.dependency_overrides[get_store] = lambda: store
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/modes")
    assert response.json()["modes"][0]["available"] is False
    assert response.json()["modes"][0]["deep_link"] is None
    channel.conversation_link.assert_not_awaited()
    assert response.json()["access"] == {
        "tier": "trial", "messages_used": 0, "message_limit": settings.trial_message_limit,
    }


async def test_live_granted_mode_has_no_link_when_processing_guard_denies(monkeypatch):
    from src.api import modes

    guard = AsyncMock(return_value="Awaiting privacy readiness")
    definition = SimpleNamespace(
        id="coach",
        name="Coach",
        purpose="One goal",
        status="live",
        entitlement="grant",
        entry_guard=guard,
    )
    monkeypatch.setattr(modes, "build_registry", lambda: [definition])
    store = SimpleNamespace(
        count_participant_messages=AsyncMock(return_value=0),
        get_active_session=AsyncMock(return_value=None),
        list_mode_conversations=AsyncMock(return_value=[]),
        get_active_mode_grant=AsyncMock(return_value={"expires_at": "2026-11-01"}),
    )
    channel = SimpleNamespace(
        channel_id="fake", recipient_for=AsyncMock(return_value=42), conversation_link=AsyncMock()
    )
    app = FastAPI()
    app.include_router(router)
    app.state.channel = channel
    app.dependency_overrides[get_activated_user] = lambda: {"user_id": "owner"}
    app.dependency_overrides[get_store] = lambda: store
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/modes")
    assert response.json()["modes"][0]["available"] is False
    assert response.json()["modes"][0]["deep_link"] is None
    assert guard.await_args.args[0].user["user_id"] == "owner"
    channel.conversation_link.assert_not_awaited()
