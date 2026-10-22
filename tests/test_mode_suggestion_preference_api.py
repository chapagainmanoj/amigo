"""Participant preference is explicit, authenticated and independent of release readiness."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.mode_suggestions import router
from src.auth import get_authenticated_user_id
from src.memory.memory_store import InMemoryStore
from tests.fakes import FakeStore
from tests.test_modes import _participant


@pytest.mark.parametrize("store_type", [FakeStore, InMemoryStore])
async def test_owned_preference_default_off_strict_boolean_and_persistent_stop(store_type):
    store = store_type()
    owner = await _participant(store, 921001)
    other = await _participant(store, 921002)
    store.get_activation_state = AsyncMock(return_value={"completed": True})
    app = FastAPI()
    app.state.store = store
    app.include_router(router)
    actor = {"id": owner["supabase_auth_id"]}
    app.dependency_overrides[get_authenticated_user_id] = lambda: actor["id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = "/api/mode-suggestions/preference"
        response = await client.get(path)
        assert response.json() == {"enabled": False}
        assert response.headers["cache-control"] == "no-store"
        assert (await client.post(path, json={"enabled": "true"})).status_code == 422
        assert (
            await client.post(path, json={"enabled": True, "user_id": other["user_id"]})
        ).status_code == 422
        assert (await client.post(path, json={"enabled": True})).json() == {"enabled": True}
        session = await store.create_session(owner["user_id"])
        offer = await store.create_mode_suggestion(
            owner["user_id"], session["session_id"], "coach", grant_required=False
        )
        assert offer
        assert (await client.post(path, json={"enabled": False})).json() == {"enabled": False}
        assert (await store.get_mode_suggestion(owner["user_id"], offer["offer_id"]))[
            "state"
        ] == "declined"
        actor["id"] = other["supabase_auth_id"]
        assert (await client.get(path)).json() == {"enabled": False}
