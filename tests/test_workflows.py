"""Workflow inspection and process-replacement contracts over existing durable Coach state."""

import copy
import json
from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI

from src.api.coaching import router
from src.api.dependencies import get_activated_user
from src.memory.memory_store import InMemoryStore
from src.scheduler.coaching import CoachingDeliveryWorker
from src.workflows import COACH_WORKFLOW_V1, coaching_workflow_status
from tests.fakes import FakeChannel, FakeStore
from tests.test_coaching_delivery import Clock
from tests.test_coaching_delivery import setup as setup  # noqa: F401 - shared workflow fixture


@pytest.mark.parametrize("store_type", [InMemoryStore, FakeStore])
async def test_unapproved_draft_survives_inspection_and_remains_owned(store_type):
    store = store_type()
    user = await store.create_user(88191)
    other = await store.create_user(88192)
    result = await store.draft_coaching_program(
        user["user_id"],
        "draft",
        "draft",
        goal="Private fictional goal",
        success_measure="Private fictional measure",
        check_in_days=[4],
        check_in_time="12:00",
        timezone="UTC",
    )
    program = result["program"]
    first = await coaching_workflow_status(store, user["user_id"], program["program_id"])
    second = await coaching_workflow_status(store, user["user_id"], program["program_id"])
    assert first == second
    assert first["waiting_for"] == "participant_approval"
    assert first["definition"]["version"] == 1
    assert first["version_binding"] == "current_code_only"
    assert "Private fictional" not in json.dumps(first)
    assert await coaching_workflow_status(store, other["user_id"], program["program_id"]) is None
    assert (await store.get_coaching_program(user["user_id"]))["state"] == "draft"
    assert await store.get_coaching_delivery_history(user["user_id"], program["program_id"]) == {
        "deliveries": [],
        "last_reply_at": None,
    }
    await store.delete_coaching_data(user["user_id"], "verified-workflow-deletion")
    assert await coaching_workflow_status(store, user["user_id"], program["program_id"]) is None


@pytest.mark.parametrize("threads", [False, True])
@pytest.mark.parametrize("crash_point", ["enqueued", "claimed", "dispatched", "accepted"])
async def test_process_replacement_preserves_occurrence_and_delivery_uncertainty(
    setup, threads, crash_point
):
    store, _, user, program, original, state = setup
    assert await original.reconcile() == 1
    claim = None
    if crash_point != "enqueued":
        claim = (await store.claim_coaching_deliveries("dead-process"))[0]
    if crash_point in {"dispatched", "accepted"}:
        assert await store.mark_coaching_dispatch(
            user["user_id"], claim["delivery_key"], claim["claim_token"]
        )
    if crash_point == "accepted":
        assert await store.finish_coaching_delivery(
            user["user_id"], claim["delivery_key"], claim["claim_token"], "accepted"
        )
    if claim:
        state["now"] += timedelta(minutes=6)
    before = copy.deepcopy(store.proactive.deliveries)
    snapshot = await coaching_workflow_status(store, user["user_id"], program["program_id"])
    assert snapshot["waiting_for"] in {"delivery_outcome", "selected_slot_or_participant_reply"}
    assert store.proactive.deliveries == before  # Inspection never takes over an execution lease.
    channel = FakeChannel(threads=threads)
    replacement = CoachingDeliveryWorker(store, channel, clock=Clock(state), admission_enabled=True)
    assert await replacement.reconcile() == 0
    assert await replacement.drain_once() == int(crash_point in {"enqueued", "claimed"})
    assert len(store.proactive.deliveries) == 1
    current = (await coaching_workflow_status(store, user["user_id"], program["program_id"]))[
        "deliveries"
    ][0]
    assert current["state"] == ("uncertain" if crash_point == "dispatched" else "accepted")
    assert await replacement.drain_once() == 0
    assert len(channel.sent) == int(crash_point in {"enqueued", "claimed"})
    if crash_point == "claimed":
        assert not await store.mark_coaching_dispatch(
            user["user_id"], claim["delivery_key"], claim["claim_token"]
        )


async def test_reply_wait_survives_worker_replacement_and_requires_own_reply(setup):
    store, channel, user, program, worker, state = setup
    assert await worker.reconcile() == 1
    assert await worker.drain_once() == 1
    state["now"] += timedelta(days=1)
    assert await worker.reconcile() == 1
    assert await worker.drain_once() == 1
    assert (await coaching_workflow_status(store, user["user_id"], program["program_id"]))[
        "waiting_for"
    ] == "participant_reply"
    state["now"] += timedelta(days=1)
    replacement = CoachingDeliveryWorker(store, channel, clock=Clock(state), admission_enabled=True)
    assert await replacement.reconcile() == 0
    other = await store.create_user(88193)
    assert not await store.note_coaching_reply(other["user_id"], program["program_id"])
    assert await replacement.reconcile() == 0
    await store.proactive.note_reply(user["user_id"], program["program_id"])
    assert await replacement.reconcile() == 1


async def test_workflow_endpoint_never_exposes_another_owner_or_execution_secrets(setup):
    store, _, user, program, worker, _ = setup
    assert await worker.reconcile() == 1
    await store.claim_coaching_deliveries("secret-worker")
    app = FastAPI()
    app.state.store = store
    app.include_router(router)
    app.dependency_overrides[get_activated_user] = lambda: user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/coaching/workflow", params={"program_id": program["program_id"]}
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["waiting_for"] == "delivery_outcome"
        assert "claim_token" not in response.text and "secret-worker" not in response.text
        other = await store.create_user(88194)
        app.dependency_overrides[get_activated_user] = lambda: other
        response = await client.get(
            "/api/coaching/workflow", params={"program_id": program["program_id"]}
        )
        assert response.status_code == 200 and response.json() is None
    assert COACH_WORKFLOW_V1.steps[0].confirmation == "exact_current_draft"


@pytest.mark.parametrize(
    "state, waiting",
    [
        ("paused", "explicit_resume"),
        ("stopped", "none"),
        ("completed", "none"),
    ],
)
async def test_terminal_or_paused_workflow_does_not_advertise_a_timer_resume(setup, state, waiting):
    store, _, user, program, _, _ = setup
    program["state"] = state
    view = await coaching_workflow_status(store, user["user_id"], program["program_id"])
    assert view["waiting_for"] == waiting
    assert not store.proactive.deliveries


async def test_only_coach_declares_the_existing_workflow_and_cross_mode_attachment_is_refused():
    from dataclasses import replace

    from src.agent.catalogue import COACH, DAILY

    assert COACH.workflows == (COACH_WORKFLOW_V1,)
    assert DAILY.workflows == ()
    with pytest.raises(ValueError, match="declaring Mode"):
        replace(DAILY, workflows=(COACH_WORKFLOW_V1,))
    with pytest.raises(ValueError, match="unique"):
        replace(COACH, workflows=(COACH_WORKFLOW_V1, COACH_WORKFLOW_V1))
