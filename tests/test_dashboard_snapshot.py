"""Canonical dashboard snapshot contract tests."""

from datetime import datetime

import httpx
from fastapi import FastAPI

from src.api.dashboard import router
from src.api.dependencies import get_activated_user
from src.dashboard_snapshot import build_dashboard_snapshot
from src.utils import UTC
from tests.fakes import FakeStore


def test_snapshot_populations_reminders_and_stale_sessions_are_consistent():
    user = {"user_id": "u1", "timezone": "Asia/Kathmandu", "session_timeout_minutes": 120}
    tasks = [
        {
            "task_id": "today-pending",
            "title": "Today",
            "status": "pending",
            "due_date": "2026-09-01",
            "created_at": "3",
            "version": 1,
        },
        {
            "task_id": "today-done",
            "title": "Done",
            "status": "completed",
            "due_date": "2026-09-01",
            "created_at": "2",
            "version": 2,
        },
        {
            "task_id": "inbox",
            "title": "Inbox",
            "status": "pending",
            "due_date": None,
            "created_at": "1",
            "version": 1,
        },
        {
            "task_id": "carried",
            "title": "Carry",
            "status": "pending",
            "due_date": "2026-08-31",
            "created_at": "0",
            "version": 1,
        },
    ]
    reminders = [
        {
            "reminder_id": "r1",
            "task_id": "carried",
            "status": "pending",
            "scheduled_time": "2026-08-31T18:00:00+00:00",
            "intended_local_date": "2026-08-31",
            "intended_local_time": "23:45:00",
            "intended_timezone": "Asia/Kathmandu",
        },
        {
            "reminder_id": "orphan",
            "task_id": "other",
            "status": "pending",
            "scheduled_time": "2026-09-01T01:00:00+00:00",
            "intended_local_date": "2026-09-01",
            "intended_local_time": "06:45:00",
            "intended_timezone": "Asia/Kathmandu",
        },
    ]
    sessions = [
        {
            "session_id": "s1",
            "started_at": "2026-08-31T12:00:00+00:00",
            "last_activity_at": "2026-08-31T12:30:00+00:00",
            "ended_at": None,
            "session_type": "structured_problem_solving",
            "context_summary": None,
        }
    ]

    snapshot = build_dashboard_snapshot(
        user,
        tasks,
        reminders,
        sessions,
        generated_at=datetime(2026, 8, 31, 19, 0, tzinfo=UTC),
    )

    assert snapshot["planning_day"] == "2026-09-01"
    assert {task["task_id"] for task in snapshot["tasks"]["today"]} == {
        "today-pending",
        "today-done",
    }
    assert snapshot["progress"] == {"completed": 1, "total": 2}
    assert [task["task_id"] for task in snapshot["tasks"]["inbox"]] == ["inbox"]
    assert [task["task_id"] for task in snapshot["tasks"]["carried_over"]] == ["carried"]
    assert [item["reminder_id"] for item in snapshot["reminders"]] == ["r1"]
    assert snapshot["reminders"][0]["task"]["population"] == "carried_over"
    assert snapshot["reminders"][0]["delivery_state"] == "overdue"
    assert snapshot["sessions"][0]["state"] == "inactive"
    assert snapshot["sessions"][0]["label"] == "Inactive conversation"
    assert snapshot["sessions"][0]["session_type_label"] == "Structured Problem Solving"


async def test_authenticated_snapshot_is_tenant_scoped_and_replaced_as_one_document():
    store = FakeStore()
    owner = await store.create_user(1)
    other = await store.create_user(2)
    await store.update_user(owner["user_id"], {"supabase_auth_id": "auth-1", "timezone": "UTC"})
    await store.create_task_command(
        user_id=owner["user_id"],
        idempotency_key="one",
        payload_hash="a" * 64,
        title="Owned",
        category="other",
        due_date=None,
        session_id=None,
    )
    await store.create_task_command(
        user_id=other["user_id"],
        idempotency_key="two",
        payload_hash="b" * 64,
        title="Other",
        category="other",
        due_date=None,
        session_id=None,
    )
    app = FastAPI()
    app.state.store = store
    app.include_router(router)
    app.dependency_overrides[get_activated_user] = lambda: owner

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/dashboard/snapshot")

    assert response.status_code == 200
    snapshot = response.json()
    assert snapshot["snapshot_version"]
    assert snapshot["generated_at"]
    assert [task["title"] for task in snapshot["tasks"]["inbox"]] == ["Owned"]
