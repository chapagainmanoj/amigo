"""Dashboard-first Activation Journey contract and cross-store regressions."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI

from src.activation import (
    ACTIVATION_POLICY_VERSION,
    ACTIVATION_TEST_TASK_TITLE,
    derive_activation_state,
    proposed_test_time,
    validate_preferred_name,
    validate_quiet_hours,
    validate_timezone,
)
from src.api.activation import router as activation_router
from src.api.dashboard import router as dashboard_router
from src.api.dependencies import get_store
from src.api.pairing import router as pairing_router
from src.api.reminders import router as reminder_router
from src.api.tasks import router as task_router
from src.auth import (
    AuthenticatedIdentity,
    get_authenticated_identity,
    get_authenticated_user_id,
)
from src.commands.activation import CreateActivationTestCommand
from src.commands.base import CommandContext, IdempotencyConflictError
from src.commands.tasks import ResolveTaskCommand
from src.memory.memory_store import InMemoryStore
from src.utils import Clock, utc_now
from tests.fakes import FakeStore


class FixedClock(Clock):
    def __init__(self, instant: datetime):
        self.instant = instant

    def utc_now(self) -> datetime:
        return self.instant


def _users(store) -> list[dict]:
    if isinstance(store, FakeStore):
        return list(store.users.values())
    return list(store._users.values())


def _tasks(store) -> list[dict]:
    return store.tasks if isinstance(store, FakeStore) else list(store._tasks.values())


def _reminders(store) -> list[dict]:
    return store.reminders if isinstance(store, FakeStore) else list(store._reminders.values())


async def _paired_profile(store, auth_id: str = "auth-activation") -> dict:
    await store.acknowledge_activation_terms(auth_id, ACTIVATION_POLICY_VERSION)
    user = await store.create_user(12345)
    await store.update_user(user["user_id"], {"supabase_auth_id": auth_id})
    await store.update_activation_profile(
        auth_id,
        name="Mano Rai",
        timezone="Asia/Kathmandu",
        wake_time="07:30",
        sleep_time="23:00",
    )
    return next(candidate for candidate in _users(store) if candidate["user_id"] == user["user_id"])


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_activation_resumes_first_incomplete_step(store_factory):
    store = store_factory()
    auth_id = "auth-resume"

    assert (await store.get_activation_state(auth_id))["step"] == "limits"
    await store.acknowledge_activation_terms(auth_id, ACTIVATION_POLICY_VERSION)
    assert (await store.get_activation_state(auth_id))["step"] == "telegram"

    user = await store.create_user(12345)
    await store.update_user(user["user_id"], {"supabase_auth_id": auth_id})
    assert (await store.get_activation_state(auth_id))["step"] == "profile"

    await store.update_activation_profile(
        auth_id,
        name="Mano",
        timezone="Asia/Kathmandu",
        wake_time="07:30",
        sleep_time="23:00",
    )
    assert (await store.get_activation_state(auth_id))["step"] == "test_reminder"


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_activation_requires_real_delivery_and_resolution(store_factory):
    store = store_factory()
    auth_id = "auth-complete"
    user = await _paired_profile(store, auth_id)
    now = utc_now()
    scheduled = now.replace(tzinfo=UTC) + timedelta(minutes=2)
    result = await CreateActivationTestCommand(store, FixedClock(now)).run(
        CommandContext(user["user_id"], "dashboard", "activation-test"),
        scheduled_at=scheduled,
        timezone="Asia/Kathmandu",
    )

    state = await store.get_activation_state(auth_id)
    assert state["step"] == "resolve"
    assert state["completed"] is False
    assert result["task"]["title"] == ACTIVATION_TEST_TASK_TITLE
    assert len(_tasks(store)) == 1
    assert len(_reminders(store)) == 1

    reminder = _reminders(store)[0]
    reminder["status"] = "sent"
    reminder["telegram_message_id"] = 9001
    await ResolveTaskCommand(store).run(
        CommandContext(user["user_id"], "telegram", "activation-done"),
        task_id=result["task"]["task_id"],
        outcome="completed",
        acted_reminder_id=reminder["reminder_id"],
    )

    completed = await store.get_activation_state(auth_id)
    assert completed["completed"] is True
    assert completed["step"] == "dashboard"
    assert completed["test"]["delivered"] is True
    assert completed["test"]["resolution"] == "done"
    assert completed["completed_at"] is not None


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_activation_test_is_idempotent_and_conflict_safe(store_factory):
    store = store_factory()
    user = await _paired_profile(store, "auth-idempotent")
    now = utc_now()
    scheduled = now.replace(tzinfo=UTC) + timedelta(minutes=2)
    command = CreateActivationTestCommand(store, FixedClock(now))
    context = CommandContext(user["user_id"], "dashboard", "same-key")

    first = await command.run(context, scheduled_at=scheduled, timezone="Asia/Kathmandu")
    replay = await command.run(context, scheduled_at=scheduled, timezone="Asia/Kathmandu")
    assert replay == first
    assert len(_tasks(store)) == 1
    assert len(_reminders(store)) == 1

    with pytest.raises(IdempotencyConflictError):
        await command.run(
            context,
            scheduled_at=scheduled + timedelta(seconds=1),
            timezone="Asia/Kathmandu",
        )


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_activation_profile_is_locked_after_test_is_scheduled(store_factory):
    store = store_factory()
    user = await _paired_profile(store, "auth-profile-lock")
    now = utc_now()
    await CreateActivationTestCommand(store, FixedClock(now)).run(
        CommandContext(user["user_id"], "dashboard", "activation-profile-lock"),
        scheduled_at=now.replace(tzinfo=UTC) + timedelta(minutes=2),
        timezone="Asia/Kathmandu",
    )

    with pytest.raises(ValueError, match="locked"):
        await store.update_activation_profile(
            "auth-profile-lock",
            name="Changed after scheduling",
            timezone="UTC",
            wake_time="08:00",
            sleep_time="22:00",
        )


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_activation_never_retries_an_in_flight_delivery(store_factory):
    store = store_factory()
    user = await _paired_profile(store, "auth-in-flight")
    now = utc_now()
    command = CreateActivationTestCommand(store, FixedClock(now))
    await command.run(
        CommandContext(user["user_id"], "dashboard", "activation-in-flight"),
        scheduled_at=now.replace(tzinfo=UTC) + timedelta(minutes=2),
        timezone="Asia/Kathmandu",
    )
    reminder = _reminders(store)[0]
    reminder["status"] = "sending"
    reminder["scheduled_time"] = (now.replace(tzinfo=UTC) - timedelta(minutes=1)).isoformat()

    state = await store.get_activation_state("auth-in-flight")
    assert state["test"]["delivery_state"] == "scheduled"
    assert state["test"]["can_retry"] is False
    with pytest.raises(ValueError, match="not eligible"):
        await command.run(
            CommandContext(user["user_id"], "dashboard", "activation-in-flight-retry"),
            scheduled_at=now.replace(tzinfo=UTC) + timedelta(minutes=3),
            timezone="Asia/Kathmandu",
            retry=True,
        )


@pytest.mark.parametrize("store_factory", [FakeStore, InMemoryStore])
async def test_dashboard_originated_resolution_cannot_complete_activation(store_factory):
    store = store_factory()
    user = await _paired_profile(store, "auth-dashboard-resolution")
    now = utc_now()
    result = await CreateActivationTestCommand(store, FixedClock(now)).run(
        CommandContext(user["user_id"], "dashboard", "activation-for-dashboard"),
        scheduled_at=now.replace(tzinfo=UTC) + timedelta(minutes=2),
        timezone="Asia/Kathmandu",
    )
    reminder = _reminders(store)[0]
    reminder["status"] = "sent"
    reminder["telegram_message_id"] = 444
    await ResolveTaskCommand(store).run(
        CommandContext(user["user_id"], "dashboard", "dashboard-resolve-test"),
        task_id=result["task"]["task_id"],
        outcome="completed",
    )

    state = await store.get_activation_state("auth-dashboard-resolution")
    assert state["completed"] is False
    assert state["test"]["resolution"] is None
    stored_user = next(
        candidate for candidate in _users(store) if candidate["user_id"] == user["user_id"]
    )
    assert stored_user["onboarding_complete"] is False


def test_activation_profile_and_exact_time_validation():
    assert validate_preferred_name("  Mano   Rai ") == "Mano Rai"
    assert validate_timezone("UTC") == "UTC"
    assert validate_timezone("Asia/Kathmandu") == "Asia/Kathmandu"
    assert validate_quiet_hours("07:30", "23:00") == ("07:30", "23:00")
    with pytest.raises(ValueError, match="IANA"):
        validate_timezone("Nepal")
    with pytest.raises(ValueError, match="differ"):
        validate_quiet_hours("07:30", "07:30")

    proposal = proposed_test_time("Asia/Kathmandu", datetime(2026, 9, 1, 0, 0))
    assert proposal == {
        "scheduled_at": "2026-09-01T00:02:00+00:00",
        "local_date": "2026-09-01",
        "local_time": "05:47:00",
        "timezone": "Asia/Kathmandu",
    }


async def test_activation_api_enforces_verified_order_and_exact_confirmation():
    store = InMemoryStore()
    identity = AuthenticatedIdentity("auth-api", True, "person@example.test")
    app = FastAPI()
    app.state.store = store
    app.include_router(activation_router)

    async def authenticated_identity():
        return identity

    async def configured_store():
        return store

    app.dependency_overrides[get_authenticated_identity] = authenticated_identity
    app.dependency_overrides[get_store] = configured_store
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        initial = await client.get("/api/activation")
        assert initial.status_code == 200
        assert initial.json()["step"] == "limits"

        incomplete = await client.post(
            "/api/activation/acknowledge",
            json={
                "policy_version": ACTIVATION_POLICY_VERSION,
                "beta_limits": True,
                "privacy_and_retention": True,
                "participant_rights": False,
                "non_clinical": True,
            },
        )
        assert incomplete.status_code == 422

        accepted = await client.post(
            "/api/activation/acknowledge",
            json={
                "policy_version": ACTIVATION_POLICY_VERSION,
                "beta_limits": True,
                "privacy_and_retention": True,
                "participant_rights": True,
                "non_clinical": True,
            },
        )
        assert accepted.status_code == 200
        assert accepted.json()["step"] == "telegram"

        user = await store.create_user(9876)
        await store.update_user(user["user_id"], {"supabase_auth_id": identity.auth_id})
        profile = await client.post(
            "/api/activation/profile",
            json={
                "preferred_name": "  Test   Person ",
                "timezone": "America/Toronto",
                "wake_time": "07:00",
                "sleep_time": "22:30",
            },
        )
        assert profile.status_code == 200
        profile_state = profile.json()
        assert profile_state["step"] == "test_reminder"
        assert profile_state["profile"]["name"] == "Test Person"
        proposal = profile_state["proposal"]

        unconfirmed = await client.post(
            "/api/activation/test-reminder",
            headers={"Idempotency-Key": "activation-api-test"},
            json={
                "scheduled_at": proposal["scheduled_at"],
                "timezone": proposal["timezone"],
                "exact_time_confirmed": False,
            },
        )
        assert unconfirmed.status_code == 422
        assert not _tasks(store)

        created = await client.post(
            "/api/activation/test-reminder",
            headers={"Idempotency-Key": "activation-api-test"},
            json={
                "scheduled_at": proposal["scheduled_at"],
                "timezone": proposal["timezone"],
                "exact_time_confirmed": True,
            },
        )
        assert created.status_code == 202
        assert created.json()["task"]["title"] == ACTIVATION_TEST_TASK_TITLE


async def test_unverified_activation_api_stays_at_email_verification():
    store = FakeStore()
    app = FastAPI()
    app.state.store = store
    app.include_router(activation_router)

    async def unverified_identity():
        return AuthenticatedIdentity("auth-unverified", False, "person@example.test")

    app.dependency_overrides[get_authenticated_identity] = unverified_identity
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        state = await client.get("/api/activation")
        assert state.json()["step"] == "email_verification"
        response = await client.post(
            "/api/activation/acknowledge",
            json={
                "policy_version": ACTIVATION_POLICY_VERSION,
                "beta_limits": True,
                "privacy_and_retention": True,
                "participant_rights": True,
                "non_clinical": True,
            },
        )
        assert response.status_code == 403


async def test_pairing_api_discloses_no_raw_token_and_enforces_journey_order(monkeypatch):
    store = FakeStore()
    identity = AuthenticatedIdentity("auth-pairing-api", True, "person@example.test")
    app = FastAPI()
    app.state.store = store
    app.state.bot_username = "test_amigo_bot"
    app.include_router(pairing_router)

    async def authenticated_identity():
        return identity

    async def configured_store():
        return store

    app.dependency_overrides[get_authenticated_identity] = authenticated_identity
    app.dependency_overrides[get_store] = configured_store
    monkeypatch.setattr("src.api.pairing.settings.access_mode", "open")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        blocked = await client.post("/api/pairing-token")
        assert blocked.status_code == 403

        await store.acknowledge_activation_terms(identity.auth_id, ACTIVATION_POLICY_VERSION)
        issued = await client.post("/api/pairing-token")
        assert issued.status_code == 200
        payload = issued.json()
        assert set(payload) == {"bot_link", "expires_at"}
        assert payload["bot_link"].startswith("https://t.me/test_amigo_bot?start=pair_")
        token = payload["bot_link"].rsplit("pair_", 1)[1]
        assert len(token) == 32
        assert token not in str(payload).replace(payload["bot_link"], "")


async def test_normal_dashboard_apis_are_server_gated_until_activation_completes():
    store = FakeStore()
    auth_id = "auth-server-gate"
    user = await _paired_profile(store, auth_id)
    now = utc_now()
    result = await CreateActivationTestCommand(store, FixedClock(now)).run(
        CommandContext(user["user_id"], "dashboard", "server-gate-test"),
        scheduled_at=now.replace(tzinfo=UTC) + timedelta(minutes=2),
        timezone="Asia/Kathmandu",
    )
    app = FastAPI()
    app.state.store = store
    app.include_router(dashboard_router)
    app.include_router(task_router)
    app.include_router(reminder_router)

    async def authenticated_user_id():
        return auth_id

    async def configured_store():
        return store

    app.dependency_overrides[get_authenticated_user_id] = authenticated_user_id
    app.dependency_overrides[get_store] = configured_store
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/dashboard/snapshot")).status_code == 409
        assert (
            await client.post(
                "/api/tasks",
                headers={"Idempotency-Key": "blocked-create"},
                json={"title": "Must not be created"},
            )
        ).status_code == 409
        assert (
            await client.post(
                f"/api/reminders/{result['reminder']['reminder_id']}/later",
                headers={"Idempotency-Key": "blocked-later"},
                json={"expected_task_version": result["task"]["version"]},
            )
        ).status_code == 409

        reminder = _reminders(store)[0]
        reminder["status"] = "sent"
        reminder["telegram_message_id"] = 555
        await ResolveTaskCommand(store).run(
            CommandContext(user["user_id"], "telegram", "telegram-gate-done"),
            task_id=result["task"]["task_id"],
            outcome="completed",
            acted_reminder_id=reminder["reminder_id"],
        )
        snapshot_response = await client.get("/api/dashboard/snapshot")

    assert snapshot_response.status_code == 200
    snapshot = snapshot_response.json()
    assert snapshot["activation"]["completed"] is True
    assert snapshot["activation"]["test"]["resolution"] == "done"


def test_activation_state_tolerates_a_null_deferred_count():
    """`tasks.deferred_count` is nullable, so a NULL must not crash the derivation.

    Regression: `task.get("deferred_count", 0)` returns None for a present-but-NULL
    column, and comparing that to 0 raised TypeError.
    """
    now = utc_now().replace(tzinfo=UTC)
    state = derive_activation_state(
        auth_id="auth-1",
        journey={
            "policy_version": "2026-08-29",
            "acknowledged_at": now.isoformat(),
            "profile_completed_at": now.isoformat(),
            "version": 3,
        },
        user={"name": "A", "timezone": "UTC", "wake_time": "07:00", "sleep_time": "22:30"},
        pairing_token=None,
        task={"title": "t", "status": "pending", "deferred_count": None, "version": 2},
        reminder={"status": "acknowledged", "telegram_message_id": 1, "scheduled_time": None},
        occurrence=None,
        now=now,
    )

    assert state["test"]["resolution"] is None
    assert state["test"]["task"]["deferred_count"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("preferred_name", "   "),
        ("preferred_name", "Jo\x01e"),
        ("timezone", "Narnia"),
        ("wake_time", "7am"),
    ],
)
async def test_activation_profile_rejects_bad_input_with_400(field, value):
    """Invalid profile input is ordinary bad input, not a server fault.

    Regression: the validators sat outside the try block with no ValueError handler,
    so every rejection surfaced as a 500.
    """
    payload = {
        "preferred_name": "Test Person",
        "timezone": "America/Toronto",
        "wake_time": "07:00",
        "sleep_time": "22:30",
    }
    payload[field] = value

    store = InMemoryStore()
    identity = AuthenticatedIdentity("auth-badinput", True, "person@example.test")
    app = FastAPI()
    app.state.store = store
    app.include_router(activation_router)

    async def authenticated_identity():
        return identity

    async def configured_store():
        return store

    app.dependency_overrides[get_authenticated_identity] = authenticated_identity
    app.dependency_overrides[get_store] = configured_store
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/activation/acknowledge",
            json={
                "policy_version": ACTIVATION_POLICY_VERSION,
                "beta_limits": True,
                "privacy_and_retention": True,
                "participant_rights": True,
                "non_clinical": True,
            },
        )
        response = await client.post("/api/activation/profile", json=payload)

    assert response.status_code == 400, response.text
