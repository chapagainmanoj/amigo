"""Transcript DTO stays separate from owned Message provenance metadata."""

import pytest

from src.memory.memory_store import InMemoryStore
from tests.fakes import FakeStore


@pytest.mark.parametrize("store_type", [InMemoryStore, FakeStore])
async def test_transcript_contains_only_role_content_created_at(store_type):
    store = store_type()
    user = await store.create_user(8811801)
    session = await store.create_session(user["user_id"])
    await store.add_message(session["session_id"], user["user_id"], "user", "Fictional text")
    rows = await store.get_session_messages(session["session_id"])
    assert len(rows) == 1
    assert set(rows[0]) == {"role", "content", "created_at"}
    rows[0]["content"] = "Detached transcript"
    assert (await store.get_session_messages(session["session_id"]))[0][
        "content"
    ] == "Fictional text"
    source = await store.get_memory_source_message(user["user_id"], session["session_id"])
    assert source["message_id"] and source["user_id"] == user["user_id"]
