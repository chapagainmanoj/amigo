"""Fictional-only application trust checks; eligibility stubs are not classifier evidence."""

import asyncio
import copy
import csv
import io
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.memory import router
from src.auth import get_authenticated_user_id
from src.config import Settings
from src.memory.durable import MEMORY_POLICY_VERSION
from src.memory.memory_store import InMemoryStore
from src.memory_service import (
    MemoryController,
    MemoryReadiness,
    MemoryService,
    memories,
    memory_csv,
)
from tests.fakes import FakeChannel, FakeStore
from tests.test_mode_routing import MutableClock
from tests.test_modes import _participant


async def fictional_eligibility(payload):
    """Only an injected fixture stub; no semantic/sensitive classification claim."""
    return True


@pytest.fixture(params=[FakeStore, InMemoryStore], ids=["fake", "in-memory"])
async def memory_env(request, monkeypatch):
    clock = MutableClock()
    monkeypatch.setattr("src.memory.durable.utc_now", clock.utc_now)
    monkeypatch.setattr("src.config.settings", Settings(_env_file=None))
    store = request.param()
    owner, other = await _participant(store, 62001), await _participant(store, 62002)
    store._memory_state.admission_enabled = True
    readiness = MemoryReadiness(True, True, True, True)
    service = MemoryService(
        store, readiness=readiness, eligibility=fictional_eligibility, clock=clock
    )
    payload = dict(
        category="preference",
        text="Fictional preference for short task lists.",
        source_mode_id="daily",
        source_channel="dashboard",
        source_message_id=None,
        source_date="2026-10-22",
        creation_path="dashboard_explicit",
        scopes=["daily"],
        valid_until=None,
    )
    return SimpleNamespace(
        store=store,
        owner=owner,
        other=other,
        clock=clock,
        readiness=readiness,
        service=service,
        payload=payload,
    )


async def save(env, payload=None):
    preview = await env.service.propose(env.owner["user_id"], payload or env.payload)
    result = await env.service.confirm(
        env.owner["user_id"],
        preview["token"],
        enable_memory=True,
        policy_version=MEMORY_POLICY_VERSION,
    )
    return result["memory"], preview


async def test_default_denial_and_semantic_eligibility_fail_closed_before_candidate_storage(
    memory_env,
):
    env = memory_env
    for service in (MemoryService(env.store), MemoryService(env.store, readiness=env.readiness)):
        with pytest.raises(ValueError):
            await service.propose(env.owner["user_id"], env.payload)
        assert service._previews == {}
    assert (await env.store.export_memory_data(env.owner["user_id"]))["memories"] == []
    assert env.store._memory_state.claims == {}


async def test_first_exact_preview_is_ephemeral_owned_opt_in_atomic_and_replay_safe(memory_env):
    env = memory_env
    preview = await env.service.propose(env.owner["user_id"], env.payload)
    assert preview["requires_enable"] is True
    assert not (await env.store.get_memory_settings(env.owner["user_id"]))["enabled"]
    assert (await env.store.export_memory_data(env.owner["user_id"]))["memories"] == []
    assert env.payload["text"] not in repr(env.store._memory_state.claims)
    with pytest.raises(ValueError):
        await env.service.confirm(
            env.other["user_id"],
            preview["token"],
            enable_memory=True,
            policy_version=MEMORY_POLICY_VERSION,
        )
    with pytest.raises(ValueError):
        await env.service.confirm(env.owner["user_id"], preview["token"])
    result = await env.service.confirm(
        env.owner["user_id"],
        preview["token"],
        enable_memory=True,
        policy_version=MEMORY_POLICY_VERSION,
    )
    assert result["memory"]["text"] == env.payload["text"] and result["settings"]["enabled"]
    assert (
        await env.service.confirm(
            env.owner["user_id"],
            preview["token"],
            enable_memory=True,
            policy_version=MEMORY_POLICY_VERSION,
        )
        == result
    )
    assert len((await env.service.inspect(env.owner["user_id"]))["memories"]) == 1


async def test_preview_snapshot_bound_restart_expiry_and_next_confirm_kill(memory_env):
    env = memory_env
    original = copy.deepcopy(env.payload)
    preview = await env.service.propose(env.owner["user_id"], env.payload)
    env.payload["text"] = "Fictional later replacement, never approved."
    assert (await env.service.review_preview(env.owner["user_id"], preview["token"]))[
        "payload"
    ] == original
    restarted = MemoryService(
        env.store, readiness=env.readiness, eligibility=fictional_eligibility, clock=env.clock
    )
    with pytest.raises(ValueError):
        await restarted.confirm(env.owner["user_id"], preview["token"])
    env.readiness.enabled = False
    with pytest.raises(ValueError):
        await env.service.confirm(
            env.owner["user_id"],
            preview["token"],
            enable_memory=True,
            policy_version=MEMORY_POLICY_VERSION,
        )
    env.readiness.enabled = True
    env.clock.now += timedelta(minutes=10)
    with pytest.raises(ValueError):
        await env.service.review_preview(env.owner["user_id"], preview["token"])
    assert not env.service._previews


async def test_correction_share_reconfirm_require_exact_new_previews_and_preserve_history(
    memory_env,
):
    env = memory_env
    original, _ = await save(env)
    changed = {**env.payload, "text": "Fictional corrected preference for concise plans."}
    preview = await env.service.propose(
        env.owner["user_id"],
        changed,
        operation="correct",
        memory_id=original["memory_id"],
        expected_memory_version=1,
    )
    corrected = (await env.service.confirm(env.owner["user_id"], preview["token"]))["memory"]
    assert corrected["version"] == 2 and corrected["supersedes_version"] == 1
    rows = (await env.service.inspect(env.owner["user_id"]))["memories"]
    assert [row["state"] for row in rows] == ["superseded", "active"]
    with pytest.raises(ValueError):
        await env.service.propose(
            env.owner["user_id"],
            {**changed, "text": "Fictional unapproved"},
            operation="share",
            memory_id=original["memory_id"],
            expected_memory_version=2,
        )
    preview = await env.service.propose(
        env.owner["user_id"],
        {**changed, "scopes": ["daily", "coach"]},
        operation="share",
        memory_id=original["memory_id"],
        expected_memory_version=2,
    )
    shared = (await env.service.confirm(env.owner["user_id"], preview["token"]))["memory"]
    assert shared["scopes"] == ["coach", "daily"]
    assert (
        await env.service.read_relevant(
            env.owner["user_id"], "coach", "turn", "preference", explicit_intent=True
        )
    )["memories"] == []
    preview = await env.service.propose(
        env.owner["user_id"],
        {**changed, "scopes": ["coach", "daily"], "valid_until": "2026-11-30"},
        operation="reconfirm",
        memory_id=original["memory_id"],
        expected_memory_version=3,
    )
    assert (await env.service.confirm(env.owner["user_id"], preview["token"]))["memory"][
        "version"
    ] == 4


async def test_pause_controls_clear_candidates_and_preserve_other_setting_and_owned_records(
    memory_env,
):
    env = memory_env
    row, _ = await save(env)
    candidate = await env.service.propose(env.owner["user_id"], env.payload)
    settings = await env.store.get_memory_settings(env.owner["user_id"])
    paused = await env.service.set_pauses(
        env.owner["user_id"], settings["version"], learning=True, use=True
    )
    assert paused["learning_paused"] and paused["use_paused"]
    with pytest.raises(ValueError):
        await env.service.confirm(env.owner["user_id"], candidate["token"])
    resumed = await env.service.set_pauses(env.owner["user_id"], paused["version"], learning=False)
    assert not resumed["learning_paused"] and resumed["use_paused"]
    assert (await env.service.inspect(env.owner["user_id"]))["memories"][0]["text"] == row["text"]
    assert (
        await env.service.read_relevant(
            env.owner["user_id"], "daily", "turn", "preference", explicit_intent=True
        )
    )["memories"] == []


async def test_retrieval_explicit_daily_only_bounded_untrusted_and_use_disclosure(memory_env):
    env = memory_env
    row, _ = await save(env)
    assert (await env.service.read_relevant(env.owner["user_id"], "daily", "t0", "preference"))[
        "memories"
    ] == []
    result = await env.service.read_relevant(
        env.owner["user_id"], "daily", "t1", "preference", explicit_intent=True
    )
    assert [item["memory_id"] for item in result["memories"]] == [row["memory_id"]]
    assert result["disclosure"] == "Based on a saved memory"
    exported = await env.service.inspect(env.owner["user_id"])
    assert len(exported["uses"]) == 1 and row["text"] not in repr(exported["uses"])
    context = SimpleNamespace(
        memory_service=env.service,
        memory_request={"query": "preference", "explicit_intent": True},
        user=env.owner,
        mode_id="daily",
        turn_id="t2",
    )
    block = await memories(context)
    assert "<untrusted_saved_memories>" in block and "no Tool authority" in block
    assert await memories(SimpleNamespace()) is None


async def test_forget_and_forget_all_remove_use_and_content_but_leave_conversations(memory_env):
    env = memory_env
    row, _ = await save(env)
    await env.service.read_relevant(
        env.owner["user_id"], "daily", "t", "preference", explicit_intent=True
    )
    other_preview = await env.service.propose(env.other["user_id"], env.payload)
    await env.service.confirm(
        env.other["user_id"],
        other_preview["token"],
        enable_memory=True,
        policy_version=MEMORY_POLICY_VERSION,
    )
    with pytest.raises(ValueError):
        await env.service.forget(env.other["user_id"], row["memory_id"], 1)
    session = await env.store.create_session(env.owner["user_id"])
    await env.store.add_message(
        session["session_id"], env.owner["user_id"], "user", "Fictional conversation remains"
    )
    messages = await env.store.get_session_messages(session["session_id"])
    env.readiness.enabled = False  # Rights controls remain available after admission is killed.
    preview = await env.service.propose(env.owner["user_id"], operation="forget_all")
    assert preview["count"] == 1
    await env.service.confirm(env.owner["user_id"], preview["token"])
    owned = await env.service.inspect(env.owner["user_id"])
    assert all(item["state"] == "forgotten" and not item.get("text") for item in owned["memories"])
    assert owned["uses"] == []
    assert await env.store.get_session_messages(session["session_id"]) == messages
    assert (await env.service.inspect(env.other["user_id"]))["memories"][0]["text"] == env.payload[
        "text"
    ]


async def test_channel_preview_and_receipt_controls_fit_telegram_and_undo_save(memory_env):
    env = memory_env
    channel = FakeChannel()
    controller = MemoryController(env.service, channel, "https://example.test/#memory")
    preview = await env.service.propose(env.owner["user_id"], env.payload)
    await controller.show_preview(env.owner, 62001, preview)
    confirm = channel.sent[-1]["buttons"][0][0]["callback_data"]
    assert len(confirm.encode()) <= 64
    await controller.handle_callback(env.other, 62002, confirm)
    assert (await env.service.inspect(env.owner["user_id"]))["memories"] == []
    await controller.handle_callback(env.owner, 62001, confirm)
    receipt = channel.sent[-1]
    assert env.payload["text"] in receipt["text"]
    assert {item["text"] for item in receipt["buttons"][0]} == {
        "Edit in Inspector",
        "Forget",
        "Undo save",
    }
    undo = next(
        item["callback_data"] for item in receipt["buttons"][0] if item["text"] == "Undo save"
    )
    assert len(undo.encode()) <= 64
    await controller.handle_callback(env.owner, 62001, undo)
    assert (await env.service.inspect(env.owner["user_id"]))["memories"][0]["state"] == "forgotten"


async def test_csv_complete_inventory_use_history_and_formula_safety(memory_env):
    env = memory_env
    row, _ = await save(env, {**env.payload, "text": "=Fictional spreadsheet formula"})
    await env.service.read_relevant(
        env.owner["user_id"], "daily", "csv", "Fictional", explicit_intent=True
    )
    exported = await env.store.export_memory_data(env.owner["user_id"])
    csv_rows = list(csv.DictReader(io.StringIO(await memory_csv(exported))))
    assert {item["record_type"] for item in csv_rows} == {"memory", "use"}
    assert (
        next(item["text"] for item in csv_rows if item["record_type"] == "memory")
        == "'" + row["text"]
    )
    assert exported["memories"][0]["text"] == row["text"]


async def test_api_activated_owner_scoped_exact_previews_no_identity_spoof_and_no_errors_leak(
    memory_env, monkeypatch
):
    env = memory_env
    monkeypatch.setattr(
        env.store, "get_activation_state", AsyncMock(return_value={"completed": True})
    )
    app = FastAPI()
    app.state.store, app.state.memory_service = env.store, env.service
    app.include_router(router)
    actor = {"auth": env.owner["supabase_auth_id"]}
    app.dependency_overrides[get_authenticated_user_id] = lambda: actor["auth"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/memory")).json()["settings"]["enabled"] is False
        bad = await client.post(
            "/api/memory/preview",
            json={"text": "Fictional", "category": "preference", "user_id": env.other["user_id"]},
        )
        assert bad.status_code == 422
        preview = await client.post(
            "/api/memory/preview", json={"text": env.payload["text"], "category": "preference"}
        )
        assert preview.status_code == 200
        token = preview.json()["token"]
        actor["auth"] = env.other["supabase_auth_id"]
        denied = await client.post(
            "/api/memory/confirm",
            json={"token": token, "enable_memory": True, "policy_version": MEMORY_POLICY_VERSION},
        )
        assert denied.status_code == 409
        actor["auth"] = env.owner["supabase_auth_id"]
        assert (
            await client.post(
                "/api/memory/confirm",
                json={
                    "token": token,
                    "enable_memory": True,
                    "policy_version": MEMORY_POLICY_VERSION,
                },
            )
        ).status_code == 200
        export = await client.get("/api/memory/export?format=csv")
        assert export.status_code == 200 and "text/csv" in export.headers["content-type"]
        assert export.headers["cache-control"] == "no-store"
        monkeypatch.setattr(
            env.store,
            "set_memory_pauses",
            AsyncMock(side_effect=ValueError("secret database sentinel")),
        )
        failed = await client.post(
            "/api/memory/settings", json={"expected_version": 1, "learning": True}
        )
        assert failed.status_code == 409 and "sentinel" not in failed.text
        monkeypatch.setattr(
            env.store, "get_activation_state", AsyncMock(return_value={"completed": False})
        )
        assert (await client.get("/api/memory")).status_code == 409


async def test_expiry_timer_removes_plaintext_and_timer_bookkeeping(memory_env, monkeypatch):
    env = memory_env
    prepare = env.store.prepare_memory_confirmation

    async def short_expiry(*args, **kwargs):
        result = await prepare(*args, **kwargs)
        result["expires_at"] = (env.clock.now + timedelta(milliseconds=25)).isoformat()
        return result

    monkeypatch.setattr(env.store, "prepare_memory_confirmation", short_expiry)
    await env.service.propose(env.owner["user_id"], env.payload)
    assert len(env.service._previews) == len(env.service._expiry_handles) == 1
    await asyncio.sleep(0.05)
    assert env.service._previews == env.service._expiry_handles == {}


async def test_concurrent_prepares_cannot_exceed_plaintext_preview_limit(memory_env, monkeypatch):
    env = memory_env
    env.service.preview_limit = 1
    prepare = env.store.prepare_memory_confirmation
    both_prepared = asyncio.Event()
    count = 0

    async def concurrent_prepare(*args, **kwargs):
        nonlocal count
        result = await prepare(*args, **kwargs)
        count += 1
        if count == 2:
            both_prepared.set()
        await both_prepared.wait()
        return result

    monkeypatch.setattr(env.store, "prepare_memory_confirmation", concurrent_prepare)
    results = await asyncio.gather(
        env.service.propose(env.owner["user_id"], env.payload),
        env.service.propose(env.owner["user_id"], env.payload),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1
    assert len(env.service._previews) == len(env.service._expiry_handles) == 1


async def test_readiness_kill_during_awaited_eligibility_or_prepare_never_caches_candidate(
    memory_env, monkeypatch
):
    env = memory_env

    async def eligibility_kill(payload):
        env.readiness.enabled = False
        return True

    env.service.eligibility = eligibility_kill
    with pytest.raises(ValueError):
        await env.service.propose(env.owner["user_id"], env.payload)
    assert not env.service._previews and not env.store._memory_state.claims
    env.readiness.enabled = True
    env.service.eligibility = fictional_eligibility
    prepare = env.store.prepare_memory_confirmation

    async def prepare_kill(*args, **kwargs):
        result = await prepare(*args, **kwargs)
        env.readiness.enabled = False
        return result

    monkeypatch.setattr(env.store, "prepare_memory_confirmation", prepare_kill)
    with pytest.raises(ValueError):
        await env.service.propose(env.owner["user_id"], env.payload)
    assert not env.service._previews and not env.service._expiry_handles


async def test_optional_proposal_tool_is_unregistered_cannot_confirm_and_default_denies(memory_env):
    from src.evaluation.gate_a import tool_schema
    from src.tools.memory import MEMORY_CANDIDATES, propose_memory

    env = memory_env
    assert set(MEMORY_CANDIDATES.tools) == {"propose_memory"}
    for mode in ("daily", "coach", "reflect", "recommender"):
        assert not {"propose_memory", "confirm_memory"} & {
            tool["name"] for tool in tool_schema(mode)
        }
    result = await propose_memory(
        SimpleNamespace(deps=SimpleNamespace()), "preference", "Fictional"
    )
    assert "unavailable" in result
    assert (await env.service.inspect(env.owner["user_id"]))["memories"] == []


async def test_optional_proposal_source_date_uses_actual_owned_message_not_turn_clock(
    memory_env, monkeypatch
):
    from datetime import datetime

    from src.tools.memory import propose_memory

    env = memory_env
    for module in ("tests.fakes", "src.memory.memory_store"):
        monkeypatch.setattr(f"{module}.utc_now", lambda: datetime(2026, 9, 1, 23, 55))
    session = await env.store.create_session(env.owner["user_id"])
    source = await env.store.add_message(
        session["session_id"], env.owner["user_id"], "user", "Fictional old preference"
    )
    channel = FakeChannel()
    context = SimpleNamespace(
        store=env.store,
        session_id=session["session_id"],
        user=env.owner,
        mode_id="daily",
        channel=channel,
        chat_id=62001,
        clock=env.clock,
        memory_service=env.service,
        conversation=None,
    )
    result = await propose_memory(SimpleNamespace(deps=context), "preference", env.payload["text"])
    assert "preview was shown" in result
    preview = next(iter(env.service._previews.values()))["public"]
    assert preview["payload"]["source_message_id"] == source["message_id"]
    assert preview["payload"]["source_date"] == "2026-09-01"
    assert preview["payload"]["source_date"] != env.clock.now.date().isoformat()


@pytest.mark.parametrize("timestamp", [None, "not-a-timestamp", 123])
async def test_optional_proposal_missing_source_date_refuses_without_candidate(
    memory_env, monkeypatch, timestamp
):
    from src.tools.memory import propose_memory

    env = memory_env
    channel = FakeChannel()
    source = dict(
        message_id="00000000-0000-0000-0000-000000000001",
        user_id=env.owner["user_id"],
        role="user",
        created_at=timestamp,
    )
    source.update(mode_id="daily", channel="dashboard")
    monkeypatch.setattr(env.store, "get_memory_source_message", AsyncMock(return_value=source))
    context = SimpleNamespace(
        store=env.store,
        session_id="session",
        user=env.owner,
        mode_id="daily",
        channel=channel,
        chat_id=62001,
        clock=env.clock,
        memory_service=env.service,
        conversation=None,
    )
    result = await propose_memory(SimpleNamespace(deps=context), "preference", env.payload["text"])
    assert "recorded date" in result
    assert env.service._previews == {} and env.store._memory_state.claims == {}
