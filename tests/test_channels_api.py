"""Dashboard primary-channel choice: owned, linked-only, and never reveals provider ids."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.channels import router
from src.auth import get_authenticated_user_id
from src.memory.memory_store import InMemoryStore
from tests.fakes import FakeStore, complete_activation
from tests.test_modes import _participant


@pytest.mark.parametrize("store_type", [FakeStore, InMemoryStore])
async def test_primary_channel_is_owned_linked_only_and_hides_external_ids(store_type):
    store = store_type()
    owner = await _participant(store, 931001)
    other = await _participant(store, 931002)
    store._identity_state.link(owner["user_id"], "fake2", "secret-ext-id")
    store.get_activation_state = AsyncMock(return_value={"completed": True})
    app = FastAPI()
    app.state.store = store
    app.include_router(router)
    actor = {"id": owner["supabase_auth_id"]}
    app.dependency_overrides[get_authenticated_user_id] = lambda: actor["id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/channels")
        assert response.json() == {
            "primary_channel": "telegram", "linked": ["fake2", "telegram"], "available": [],
        }
        assert response.headers["cache-control"] == "no-store"
        assert "secret-ext-id" not in response.text and "931001" not in response.text

        path = "/api/channels/primary"
        assert (await client.post(path, json={"channel": 2})).status_code == 422
        assert (
            await client.post(path, json={"channel": "fake2", "user_id": other["user_id"]})
        ).status_code == 422
        assert (await client.post(path, json={"channel": "slack"})).status_code == 409
        switched = await client.post(path, json={"channel": "fake2"})
        assert switched.json() == {
            "primary_channel": "fake2", "linked": ["fake2", "telegram"], "available": [],
        }
        assert (await store.get_user_by_id(owner["user_id"]))["primary_channel"] == "fake2"

        actor["id"] = other["supabase_auth_id"]
        assert (await client.get("/api/channels")).json() == {
            "primary_channel": "telegram", "linked": ["telegram"], "available": [],
        }
        assert (await client.post(path, json={"channel": "fake2"})).status_code == 409


@pytest.mark.parametrize("store_type", [FakeStore, InMemoryStore])
async def test_full_access_accounts_get_a_pair_code_for_running_unlinked_apps(
    store_type, monkeypatch
):
    from src.bot.pairing import handle_pairing, pairing_token
    from src.channels.registry import ChannelRegistry
    from tests.fakes import FakeChannel

    monkeypatch.setattr("src.config.settings.allowed_telegram_chat_ids", "931101")
    store = store_type()
    owner = await _participant(store, 931101)
    trial = await _participant(store, 931102)
    for auth_id in (owner["supabase_auth_id"], trial["supabase_auth_id"]):
        await complete_activation(store, auth_id)
    store.get_activation_state = AsyncMock(return_value={"completed": True})
    discord = FakeChannel(channel_id="discord")
    discord.connect_link = "https://discord.example/install"
    app = FastAPI()
    app.state.store = store
    app.state.channels = ChannelRegistry([FakeChannel(), discord])
    app.include_router(router)
    actor = {"id": owner["supabase_auth_id"]}
    app.dependency_overrides[get_authenticated_user_id] = lambda: actor["id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/channels")).json()["available"] == ["discord"]
        assert (await client.post("/api/channels/telegram/pairing-token")).status_code == 404
        issued = await client.post("/api/channels/discord/pairing-token")
        body = issued.json()
        assert issued.status_code == 200 and issued.headers["cache-control"] == "no-store"
        assert body["app_link"] == "https://discord.example/install"
        assert body["command"].startswith("/pair ")

        # The code links Discord through the same bot-side rule.
        await handle_pairing("ext-1", pairing_token(body["command"]), store, discord)
        assert await store.list_channel_identities(owner["user_id"]) == {
            "discord": "ext-1", "telegram": "931101",
        }
        assert (await client.get("/api/channels")).json()["available"] == []
        assert (await client.post("/api/channels/discord/pairing-token")).status_code == 404

        actor["id"] = trial["supabase_auth_id"]  # not on the full-access list
        assert (await client.get("/api/channels")).json()["available"] == []
        assert (await client.post("/api/channels/discord/pairing-token")).status_code == 404
