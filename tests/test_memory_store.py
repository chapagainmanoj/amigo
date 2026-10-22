"""Memory contracts over local implementations and production RPC DTO boundary.

SQL assertions exercise PostgreSQL independently; the adapter double here forwards RPCs
into the same contract suite and does not claim to simulate SQL isolation/permissions.
"""

import asyncio
import copy
import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.commands.base import IdempotencyConflictError, InvalidTransitionError, StaleVersionError
from src.memory.durable import MEMORY_POLICY_VERSION, memory_inventory_digest, memory_payload_digest
from src.memory.memory_store import InMemoryStore
from src.memory.store import MemoryStore
from tests.fakes import FakeStore


def payload(**overrides):
    return (
        dict(
            category="preference",
            text="Fictional morning coffee",
            source_mode_id="daily",
            source_channel="dashboard",
            source_message_id=None,
            source_date="2026-10-22",
            creation_path="dashboard_explicit",
            scopes=["daily"],
            valid_until=None,
        )
        | overrides
    )


class _RPC:
    def __init__(self, backing, name, args):
        assert name in {"memory_command", "purge_memory_claims"}
        self.backing, self.args, self.name = backing, args, name

    async def execute(self):
        if self.name == "purge_memory_claims":
            return SimpleNamespace(data=await self.backing.purge_memory_claims())
        args = self.args
        result = await getattr(self.backing, args["p_operation"])(
            args["p_user_id"], **args["p_args"]
        )
        return SimpleNamespace(data=copy.deepcopy(result))


class _DB:
    def __init__(self, backing):
        self.backing = backing

    def rpc(self, name, args):
        return _RPC(self.backing, name, args)


@pytest.fixture(params=["memory", "fake", "rpc"])
async def store(request, monkeypatch):
    clock = {"now": datetime(2026, 10, 22, 12, tzinfo=UTC)}
    monkeypatch.setattr("src.memory.durable.utc_now", lambda: clock["now"])
    backing = FakeStore() if request.param == "fake" else InMemoryStore()
    user = await backing.create_user("910200001")
    other = await backing.create_user("910200002")
    adapter = backing
    if request.param == "rpc":
        adapter = MemoryStore()
        adapter.db = _DB(backing)
    return adapter, backing, user["user_id"], other["user_id"], clock


async def save(store, user, key="save", value=None, operation="save", memory=None):
    value = value or payload()
    settings = await store.get_memory_settings(user)
    claim = await store.prepare_memory_confirmation(
        user,
        operation,
        memory_payload_digest(value),
        settings["version"],
        memory["memory_id"] if memory else None,
        memory["version"] if memory else None,
    )
    return await store.confirm_memory_save(
        user,
        claim["token"],
        value,
        key,
        key,
        enable_memory=True,
        policy_version=MEMORY_POLICY_VERSION,
    )


async def test_default_off_exact_preview_atomic_opt_in_and_single_use(store):
    api, backing, user, other, _ = store
    assert (await api.get_memory_settings(user))["enabled"] is False
    with pytest.raises(InvalidTransitionError):
        await save(api, user)
    backing._memory_state.admission_enabled = True
    claim = await api.prepare_memory_confirmation(user, "save", memory_payload_digest(payload()), 0)
    assert payload()["text"] not in repr(backing._memory_state.claims)
    assert claim["token"] not in backing._memory_state.claims
    for actor, value, enabled, policy in [
        (other, payload(), True, MEMORY_POLICY_VERSION),
        (user, payload(text="Altered"), True, MEMORY_POLICY_VERSION),
        (user, payload(), False, MEMORY_POLICY_VERSION),
        (user, payload(), True, "old-policy"),
    ]:
        with pytest.raises((ValueError, InvalidTransitionError)):
            await api.confirm_memory_save(
                actor, claim["token"], value, "save", "save", enabled, policy
            )
    assert (await api.get_memory_settings(user))["enabled"] is False
    result = await api.confirm_memory_save(
        user, claim["token"], payload(), "save", "save", True, MEMORY_POLICY_VERSION
    )
    assert result["settings"]["enabled"] and result["memory"]["text"] == payload()["text"]
    assert await api.confirm_memory_save(user, claim["token"], payload(), "save", "save") == result
    with pytest.raises((StaleVersionError, InvalidTransitionError)):
        await api.confirm_memory_save(user, claim["token"], payload(), "another", "another")
    with pytest.raises(IdempotencyConflictError):
        await api.confirm_memory_save(user, claim["token"], payload(), "save", "changed")
    assert payload()["text"] not in repr(backing._memory_state.receipts)


async def test_scope_relevance_max_three_use_ledger_and_next_turn_pause(store):
    api, backing, user, other, _ = store
    backing._memory_state.admission_enabled = True
    for i in range(5):
        await save(api, user, f"save{i}", payload(text=f"Fictional morning coffee {i}"))
    assert await api.read_memory_context(other, "daily", "a", "personalize", "coffee") == []
    assert await api.read_memory_context(user, "coach", "a", "personalize", "coffee") == []
    assert await api.read_memory_context(user, "reflect", "a", "personalize", "coffee") == []
    assert await api.read_memory_context(user, "daily", "b", "personalize", "unrelated") == []
    rows = await api.read_memory_context(user, "daily", "a", "personalize", "coffee")
    assert len(rows) == 3 and all(row["untrusted"] and row["use_purpose"] for row in rows)
    await api.read_memory_context(user, "daily", "a", "personalize", "morning")
    assert len((await api.export_memory_data(user))["uses"]) == 3
    settings = await api.get_memory_settings(user)
    await api.set_memory_pauses(
        user, settings["version"], use=True, idempotency_key="pause", payload_hash="pause"
    )
    assert await api.read_memory_context(user, "daily", "next", "personalize", "coffee") == []
    assert len((await api.inspect_memories(user))["memories"]) == 5


async def test_correct_share_lifecycle_optimistic_and_purge_all_versions(store):
    api, backing, user, other, _ = store
    backing._memory_state.admission_enabled = True
    row = (await save(api, user))["memory"]
    with pytest.raises(ValueError):
        await api.forget_memory(other, row["memory_id"], 1, "foreign", "foreign")
    row = (
        await save(api, user, "correct", payload(text="Fictional tea preference"), "correct", row)
    )["memory"]
    assert row["version"] == 2 and row["supersedes_version"] == 1
    row = (
        await save(
            api, user, "share", payload(text=row["text"], scopes=["daily", "coach"]), "share", row
        )
    )["memory"]
    assert len(await api.read_memory_context(user, "coach", "a", "preference", "tea")) == 1
    row = (
        await api.transition_memory(user, row["memory_id"], 3, "inactive", "inactive", "inactive")
    )["memory"]
    assert row["version"] == 4
    with pytest.raises(StaleVersionError):
        await api.transition_memory(user, row["memory_id"], 3, "use_again", "stale", "stale")
    assert await api.read_memory_context(user, "coach", "b", "preference", "tea") == []
    await api.forget_memory(user, row["memory_id"], 4, "forget", "forget")
    data = await api.export_memory_data(user)
    assert len(data["memories"]) == 4 and data["uses"] == []
    assert all(
        r["text"] is None
        and r["source_mode_id"] is None
        and r["scopes"] == []
        and r["state"] == "forgotten"
        for r in data["memories"]
    )
    with pytest.raises(IdempotencyConflictError):
        await api.confirm_memory_save(user, "gone", payload(), "save", "save")


async def test_temporal_reconfirmation_goal_completion_and_learning_pause(store):
    api, backing, user, _, clock = store
    backing._memory_state.admission_enabled = True
    row = (
        await save(api, user, "goal", payload(category="goal", text="Fictional coffee project"))
    )["memory"]
    await api.transition_memory(user, row["memory_id"], 1, "complete_goal", "complete", "complete")
    assert await api.read_memory_context(user, "daily", "a", "suggestion", "coffee") == []
    row = (await save(api, user, "routine", payload(category="routine")))["memory"]
    clock["now"] += timedelta(days=91)
    data = await api.export_memory_data(user)
    assert (
        next(r for r in data["memories"] if r["memory_id"] == row["memory_id"])["state"]
        == "needs_confirmation"
    )
    assert await api.read_memory_context(user, "daily", "b", "personalize", "coffee") == []
    settings = await api.get_memory_settings(user)
    claim = await api.prepare_memory_confirmation(
        user, "save", memory_payload_digest(payload()), settings["version"]
    )
    await api.set_memory_pauses(
        user, settings["version"], learning=True, idempotency_key="pause", payload_hash="pause"
    )
    with pytest.raises((StaleVersionError, InvalidTransitionError)):
        await api.confirm_memory_save(user, claim["token"], payload(), "late", "late")
    assert (await api.get_memory_settings(user))["learning_paused"] is True


async def test_forget_all_exact_inventory_and_metadata_receipts(store):
    api, backing, user, _, _ = store
    backing._memory_state.admission_enabled = True
    await save(api, user)
    data = await api.export_memory_data(user)
    claim = await api.prepare_memory_confirmation(
        user, "forget_all", memory_inventory_digest(data["memories"]), data["settings"]["version"]
    )
    result = await api.confirm_forget_all_memory(user, claim["token"], "all", "all")
    assert result == {"status": "forgotten", "count": 1}
    assert await api.confirm_forget_all_memory(user, claim["token"], "all", "all") == result
    assert all(r["text"] is None for r in (await api.export_memory_data(user))["memories"])


async def test_global_five_owner_cap_counts_master_pause_and_serializes(store):
    api, backing, _, _, _ = store
    backing._memory_state.admission_enabled = True
    users = [(await backing.create_user(str(920200000 + i)))["user_id"] for i in range(8)]
    results = await asyncio.gather(*(save(api, user) for user in users), return_exceptions=True)
    assert sum(isinstance(row, dict) for row in results) == 5
    assert sum(isinstance(row, InvalidTransitionError) for row in results) == 3
    winner = next(user for user, row in zip(users, results, strict=True) if isinstance(row, dict))
    settings = await api.get_memory_settings(winner)
    await api.set_memory_pauses(
        winner,
        settings["version"],
        use=True,
        learning=True,
        idempotency_key="pause",
        payload_hash="pause",
    )
    loser = next(
        user for user, row in zip(users, results, strict=True) if isinstance(row, Exception)
    )
    with pytest.raises(InvalidTransitionError):
        await save(api, loser, "retry")


async def test_owned_provenance_and_expired_tokens_fail_before_opt_in(store):
    api, backing, user, other, clock = store
    backing._memory_state.admission_enabled = True
    session = await backing.create_session(other)
    message = await backing.add_message(session["session_id"], other, "user", "fictional source")
    value = payload(source_message_id=message["message_id"])
    with pytest.raises(ValueError):
        await save(api, user, "source", value)
    assert (await api.get_memory_settings(user))["enabled"] is False
    claim = await api.prepare_memory_confirmation(user, "save", memory_payload_digest(payload()), 0)
    clock["now"] += timedelta(minutes=11)
    with pytest.raises(InvalidTransitionError):
        await api.confirm_memory_save(
            user, claim["token"], payload(), "expired", "expired", True, MEMORY_POLICY_VERSION
        )
    assert (await api.get_memory_settings(user))["enabled"] is False


async def test_valid_until_overrides_aging_but_not_scope_or_completed_goal(store):
    api, backing, user, _, clock = store
    backing._memory_state.admission_enabled = True
    await save(api, user, "valid", payload(valid_until="2027-10-22"))
    await save(api, user, "pref", payload(text="Fictional morning coffee preference"))
    clock["now"] += timedelta(days=181)
    rows = await api.read_memory_context(user, "daily", "t1", "preference", "coffee")
    assert len(rows) == 1 and rows[0]["valid_until"] == "2027-10-22"
    clock["now"] = datetime(2027, 10, 23, tzinfo=UTC)
    assert await api.read_memory_context(user, "daily", "t2", "preference", "coffee") == []
    assert "expired" in {row["state"] for row in (await api.inspect_memories(user))["memories"]}


async def test_forget_all_inventory_stales_after_later_save_and_export_complete(store):
    api, backing, user, _, _ = store
    backing._memory_state.admission_enabled = True
    await save(api, user)
    data = await api.export_memory_data(user)
    claim = await api.prepare_memory_confirmation(
        user, "forget_all", memory_inventory_digest(data["memories"]), data["settings"]["version"]
    )
    await save(api, user, "later", payload(text="Another fictional preference"))
    with pytest.raises(StaleVersionError):
        await api.confirm_forget_all_memory(user, claim["token"], "all", "all")
    assert len((await api.inspect_memories(user, limit=1))["memories"]) == 1
    assert len((await api.export_memory_data(user))["memories"]) == 2


async def test_disable_withdraws_deletes_versions_claims_uses_and_requires_fresh_consent(store):
    api, backing, user, other, _ = store
    backing._memory_state.admission_enabled = True
    first = (await save(api, user))["memory"]
    await save(api, other, "other")
    await api.read_memory_context(user, "daily", "before-disable", "personalize", "coffee")
    await save(api, user, "correct", payload(text="Fictional coffee correction"), "correct", first)
    settings = await api.get_memory_settings(user)
    claim = await api.prepare_memory_confirmation(
        user, "save", memory_payload_digest(payload()), settings["version"]
    )
    with pytest.raises(StaleVersionError):
        await api.disable_memory(user, settings["version"] - 1, "stale-disable", "disable")
    result = await api.disable_memory(user, settings["version"], "disable", "disable")
    assert result["status"] == "disabled"
    assert result["settings"]["enabled"] is False
    assert result["settings"]["policy_version"] is None
    assert result["settings"]["opted_in_at"] is None
    data = await api.export_memory_data(user)
    assert data["memories"] == data["uses"] == []
    assert not any(row["user_id"] == user for row in backing._memory_state.claims.values())
    assert len((await api.export_memory_data(other))["memories"]) == 1
    assert await api.disable_memory(user, settings["version"], "disable", "disable") == result
    with pytest.raises(InvalidTransitionError):
        await api.confirm_memory_save(
            user, claim["token"], payload(), "save", "save", True, MEMORY_POLICY_VERSION
        )
    next_settings = await api.get_memory_settings(user)
    next_claim = await api.prepare_memory_confirmation(
        user, "save", memory_payload_digest(payload()), next_settings["version"]
    )
    with pytest.raises(InvalidTransitionError):
        await api.confirm_memory_save(user, next_claim["token"], payload(), "fresh", "fresh")
    fresh = await api.confirm_memory_save(
        user, next_claim["token"], payload(), "fresh", "fresh", True, MEMORY_POLICY_VERSION
    )
    assert fresh["memory"]["version"] == 1
    assert fresh["memory"]["memory_id"] != first["memory_id"]


async def test_disable_frees_global_trial_slot_but_pause_does_not(store):
    api, backing, user, _, _ = store
    backing._memory_state.admission_enabled = True
    await save(api, user)
    for i in range(4):
        actor = (await backing.create_user(str(930200000 + i)))["user_id"]
        await save(api, actor)
    waiting = (await backing.create_user("930200099"))["user_id"]
    with pytest.raises(InvalidTransitionError):
        await save(api, waiting)
    settings = await api.get_memory_settings(user)
    await api.disable_memory(user, settings["version"], "disable", "disable")
    assert (await save(api, waiting))["settings"]["enabled"] is True


async def test_forget_deletes_all_owned_claims_and_hashes_with_safe_scoped_replay(store):
    api, backing, user, other, _ = store
    backing._memory_state.admission_enabled = True
    row = (await save(api, user))["memory"]
    foreign = (await save(api, other, "foreign"))["memory"]
    settings = await api.get_memory_settings(user)
    await api.prepare_memory_confirmation(
        user, "save", memory_payload_digest(payload()), settings["version"]
    )
    foreign_settings = await api.get_memory_settings(other)
    await api.prepare_memory_confirmation(
        other, "save", memory_payload_digest(payload()), foreign_settings["version"]
    )
    result = await api.forget_memory(user, row["memory_id"], row["version"], "forget", "forget")
    assert not any(item["user_id"] == user for item in backing._memory_state.claims.values())
    assert all(
        item["payload_hash"] is None
        for (actor, _), item in backing._memory_state.receipts.items()
        if actor == user
    )
    assert any(item["user_id"] == other for item in backing._memory_state.claims.values())
    assert all(
        item["payload_hash"] is not None
        for (actor, _), item in backing._memory_state.receipts.items()
        if actor == other
    )
    assert (
        await api.forget_memory(user, row["memory_id"], row["version"], "forget", "forget")
        == result
    )
    with pytest.raises(IdempotencyConflictError):
        await api.forget_memory(user, foreign["memory_id"], foreign["version"], "forget", "forget")
    with pytest.raises(IdempotencyConflictError):
        await api.confirm_memory_save(
            user, "deleted", payload(), "save", "save", True, MEMORY_POLICY_VERSION
        )


async def test_claim_maintenance_purges_consumed_and_expired_but_keeps_live_and_version_history(
    store,
):
    api, backing, user, other, clock = store
    backing._memory_state.admission_enabled = True
    row = (await save(api, user, value=payload(valid_until="2026-10-23")))["memory"]
    await save(
        api,
        user,
        "correct",
        payload(text="Fictional correction", valid_until="2026-10-23"),
        "correct",
        row,
    )
    settings = await api.get_memory_settings(user)
    await api.prepare_memory_confirmation(
        user, "save", memory_payload_digest(payload()), settings["version"]
    )
    clock["now"] += timedelta(days=2)
    live = await api.prepare_memory_confirmation(other, "save", memory_payload_digest(payload()), 0)
    result = await api.purge_memory_claims()
    assert result == {"claims": 3}
    assert len(backing._memory_state.claims) == 1
    assert hashlib.sha256(live["token"].encode()).hexdigest() in backing._memory_state.claims
    history = (await api.export_memory_data(user))["memories"]
    assert len(history) == 2 and all(item["text"] for item in history)
    assert {item["state"] for item in history} == {"superseded", "expired"}
    assert await api.purge_memory_claims() == {"claims": 0}
