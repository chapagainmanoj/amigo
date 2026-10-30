"""Dashboard primary-channel choice: owned, linked-only, and never reveals provider ids."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.channels import router
from src.auth import get_authenticated_user_id
from src.memory.memory_store import InMemoryStore
from tests.fakes import FakeStore
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
        assert response.json() == {"primary_channel": "telegram", "linked": ["fake2", "telegram"]}
        assert response.headers["cache-control"] == "no-store"
        assert "secret-ext-id" not in response.text and "931001" not in response.text

        path = "/api/channels/primary"
        assert (await client.post(path, json={"channel": 2})).status_code == 422
        assert (
            await client.post(path, json={"channel": "fake2", "user_id": other["user_id"]})
        ).status_code == 422
        assert (await client.post(path, json={"channel": "slack"})).status_code == 409
        switched = await client.post(path, json={"channel": "fake2"})
        assert switched.json() == {"primary_channel": "fake2", "linked": ["fake2", "telegram"]}
        assert (await store.get_user_by_id(owner["user_id"]))["primary_channel"] == "fake2"

        actor["id"] = other["supabase_auth_id"]
        assert (await client.get("/api/channels")).json() == {
            "primary_channel": "telegram", "linked": ["telegram"],
        }
        assert (await client.post(path, json={"channel": "fake2"})).status_code == 409
