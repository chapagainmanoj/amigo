"""Versioned fictional retrieval evidence, not semantic/sensitive admission certification."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.memory.durable import MEMORY_POLICY_VERSION, memory_payload_digest
from src.memory.memory_store import InMemoryStore

SUITE = json.loads((Path(__file__).parents[1] / "evals/memory/v1/cases.json").read_text())


@pytest.mark.parametrize("case", SUITE["cases"], ids=lambda case: case["id"])
async def test_fictional_retrieval_expected_ids_scopes_and_lifecycle(case, monkeypatch):
    clock = {"now": datetime(2026, 10, 22, 12, tzinfo=UTC)}
    monkeypatch.setattr("src.memory.durable.utc_now", lambda: clock["now"])
    store = InMemoryStore()
    store._memory_state.admission_enabled = True
    user = (await store.create_user(910206001))["user_id"]
    other = (await store.create_user(910206002))["user_id"]
    identities = {}
    for item in case["items"]:
        actor = other if item.get("foreign") else user
        value = dict(
            category=item.get("category", "preference"),
            text=item["text"],
            source_mode_id="daily",
            source_channel="dashboard",
            source_message_id=None,
            source_date="2026-10-22",
            creation_path="dashboard_explicit",
            scopes=item.get("scopes", ["daily"]),
            valid_until=item.get("valid_until"),
        )
        settings = await store.get_memory_settings(actor)
        claim = await store.prepare_memory_confirmation(
            actor, "save", memory_payload_digest(value), settings["version"]
        )
        result = await store.confirm_memory_save(
            actor, claim["token"], value, item["id"], item["id"], True, MEMORY_POLICY_VERSION
        )
        row = result["memory"]
        identities[row["memory_id"]] = item["id"]
        if item.get("action"):
            await store.transition_memory(
                actor,
                row["memory_id"],
                1,
                item["action"],
                item["id"] + ":state",
                item["id"] + ":state",
            )
    if case.get("pause_use") or case.get("pause_learning"):
        settings = await store.get_memory_settings(user)
        await store.set_memory_pauses(
            user,
            settings["version"],
            use=case.get("pause_use"),
            learning=case.get("pause_learning"),
            idempotency_key="pause",
            payload_hash="pause",
        )
    clock["now"] += timedelta(days=case.get("advance_days", 0))
    rows = await store.read_memory_context(
        user, case.get("mode", "daily"), "fictional-turn", "personalize", case["query"]
    )
    assert len(rows) <= 3
    assert {identities[row["memory_id"]] for row in rows} == set(case["expected"])
    assert all(row["untrusted"] and row["use_purpose"] for row in rows)
    assert len((await store.export_memory_data(user))["uses"]) == len(rows)
