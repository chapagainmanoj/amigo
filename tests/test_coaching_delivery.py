"""Shared budget, selected-day coaching cadence, and no-retry dispatch fencing."""

import asyncio
import copy
from datetime import UTC, datetime, timedelta

import pytest

from src.memory.memory_store import InMemoryStore
from src.memory.proactive import LocalProactiveState, instant
from src.scheduler.coaching import CoachingDeliveryWorker, plan_coaching_delivery
from tests.fakes import FakeChannel, FakeStore


class DeliveryStore(FakeStore):
    """Exercise the proposed local state API without assuming shared Store integration."""

    def __init__(self):
        super().__init__()
        self.proactive = LocalProactiveState()
        self.programs = {}
        self.grants = []

    async def complete_due_coaching_programs(self):
        return []

    async def list_active_coaching_programs(self):
        return [copy.deepcopy(row) for row in self.programs.values() if row["state"] == "active"]

    async def get_coaching_program(self, user_id, program_id=None):
        row = self.programs.get(program_id)
        return copy.deepcopy(row) if row and row["user_id"] == user_id else None

    async def has_coaching_consent(self, user_id):
        return await self.proactive.has_consent(user_id)

    async def get_coaching_delivery_history(self, user_id, program_id):
        return await self.proactive.history(user_id, program_id)

    async def enqueue_coaching_delivery(
        self, user_id, program_id, expected_version, delivery_key, local_day, kind, scheduled_at
    ):
        user = await self.get_user_by_id(user_id)
        activation = await self.get_activation_state(user["supabase_auth_id"])
        return await self.proactive.enqueue(
            user,
            self.programs,
            self.grants,
            program_id,
            expected_version,
            local_day,
            kind,
            scheduled_at,
            delivery_key,
            activated=activation["completed"],
        )

    async def claim_coaching_deliveries(self, worker_id, limit=25):
        return await self.proactive.claim(worker_id, limit)

    async def mark_coaching_dispatch(self, user_id, key, token):
        user = await self.get_user_by_id(user_id)
        activation = await self.get_activation_state(user["supabase_auth_id"])
        return await self.proactive.dispatch(
            user_id,
            key,
            token,
            self.programs,
            self.grants,
            user=user,
            activated=activation["completed"],
        )

    async def finish_coaching_delivery(self, user_id, key, token, outcome):
        return await self.proactive.finish(user_id, key, token, outcome)


class Clock:
    def __init__(self, state):
        self.state = state

    def utc_now(self):
        return self.state["now"]


@pytest.fixture
async def setup(monkeypatch):
    state = {"now": datetime(2026, 10, 22, 12, tzinfo=UTC)}
    monkeypatch.setattr("src.memory.proactive.utc_now", lambda: state["now"])
    store, channel = DeliveryStore(), FakeChannel()
    user = await store.create_user(123)
    user.update(timezone="UTC", wake_time="07:30", sleep_time="23:00", daily_message_budget=4)
    from src.activation import ACTIVATION_POLICY_VERSION

    user["supabase_auth_id"] = "fictional-activation"
    await store.acknowledge_activation_terms(user["supabase_auth_id"], ACTIVATION_POLICY_VERSION)
    task = await store.create_task(user["user_id"], "Private Activation test")
    task["status"] = "completed"
    reminder = await store.create_reminder(
        task["task_id"], user["user_id"], state["now"].isoformat()
    )
    reminder.update(status="acknowledged", telegram_message_id=1)
    store.activation_journeys[user["supabase_auth_id"]].update(
        profile_completed_at=state["now"].isoformat(),
        test_task_id=task["task_id"],
        test_reminder_id=reminder["reminder_id"],
    )
    assert (await store.get_activation_state(user["supabase_auth_id"]))["completed"] is True
    program = dict(
        program_id="00000000-0000-0000-0000-000000019001",
        user_id=user["user_id"],
        version=1,
        state="active",
        timezone="UTC",
        check_in_days=list(range(1, 8)),
        check_in_time="12:00",
        starts_at=(state["now"] - timedelta(days=1)).isoformat(),
        ends_at=(state["now"] + timedelta(days=13)).isoformat(),
    )
    store.programs[program["program_id"]] = program
    store.grants.append(
        dict(
            user_id=user["user_id"], mode_id="coach", revoked_at=None, expires_at=program["ends_at"]
        )
    )
    await store.proactive.consent(user["user_id"], "coaching-v1")
    worker = CoachingDeliveryWorker(store, channel, clock=Clock(state), admission_enabled=True)
    return store, channel, user, program, worker, state


async def test_shared_budget_is_atomic_and_cannot_be_supplied_by_caller(setup):
    store, _, user, _, _, state = setup
    results = await asyncio.gather(
        *[
            store.proactive.reserve(user, f"reminder:{index}", "recovery", state["now"])
            for index in range(8)
        ]
    )
    assert sum(row["status"] == "reserved" for row in results) == 4
    assert sum(row["status"] == "budget_exhausted" for row in results) == 4


async def test_participant_reminders_do_not_create_debt_or_block_coach(setup):
    store, _, user, _, worker, state = setup
    reminders = [dict(reminder_id=str(index), user_id=user["user_id"], status="pending",
                      scheduled_time=state["now"].isoformat()) for index in range(5)]
    await store.proactive.backfill_reminders([user], reminders)
    assert store.proactive.reservations == {}
    assert await worker.reconcile() == 1


async def test_timezone_change_does_not_reopen_reserved_capacity(setup):
    store, _, user, _, _, state = setup
    user["daily_message_budget"] = 1
    at = state["now"].replace(hour=23)
    await store.proactive.reserve(user, "first", "recovery", at)
    user["timezone"] = "Pacific/Auckland"
    result = await store.proactive.reserve(user, "second", "recovery", at + timedelta(minutes=1))
    assert result["status"] == "budget_exhausted"


async def test_restarts_and_duplicate_claims_send_only_once(setup):
    store, channel, _, _, worker, _ = setup
    assert await worker.reconcile() == 1
    assert await worker.reconcile() == 0
    assert await asyncio.gather(worker.drain_once(), worker.drain_once()) == [1, 0]
    assert len(channel.sent) == 1
    assert await worker.drain_once() == 0
    assert next(iter(store.proactive.deliveries.values()))["state"] == "accepted"


async def test_timeout_is_uncertain_and_never_retried(setup, monkeypatch):
    store, channel, _, _, worker, state = setup
    await worker.reconcile()

    async def timeout(*args, **kwargs):
        raise TimeoutError("private provider response")

    monkeypatch.setattr(channel, "send_message", timeout)
    assert await worker.drain_once() == 0
    row = next(iter(store.proactive.deliveries.values()))
    assert row["state"] == "uncertain"
    state["now"] += timedelta(minutes=6)
    assert await worker.drain_once() == 0
    assert "private" not in str(row)


@pytest.mark.parametrize("change", ["pause", "revoke", "withdraw", "expire"])
async def test_dispatch_rechecks_lifecycle_grant_and_consent(setup, change):
    store, channel, user, program, worker, state = setup
    await worker.reconcile()
    if change == "pause":
        program["state"] = "paused"
    elif change == "revoke":
        store.grants[0]["revoked_at"] = state["now"].isoformat()
    elif change == "withdraw":
        await store.proactive.consent(user["user_id"])
    else:
        store.grants[0]["expires_at"] = state["now"].isoformat()
    assert await worker.drain_once() == 0
    assert not channel.sent
    assert next(iter(store.proactive.deliveries.values()))["state"] == "cancelled"


async def test_crash_after_dispatch_marker_becomes_uncertain_without_resend(setup):
    store, channel, user, _, worker, state = setup
    await worker.reconcile()
    row = (await store.claim_coaching_deliveries("crashed"))[0]
    assert await store.mark_coaching_dispatch(
        user["user_id"], row["delivery_key"], row["claim_token"]
    )
    state["now"] += timedelta(minutes=6)
    assert await worker.drain_once() == 0 and not channel.sent
    assert next(iter(store.proactive.deliveries.values()))["state"] == "uncertain"


async def test_fenced_expired_claim_cannot_finish_or_dispatch(setup):
    store, _, user, _, worker, state = setup
    await worker.reconcile()
    first = (await store.claim_coaching_deliveries("first"))[0]
    state["now"] += timedelta(minutes=6)
    second = (await store.claim_coaching_deliveries("second"))[0]
    assert first["claim_token"] != second["claim_token"]
    assert not await store.mark_coaching_dispatch(
        user["user_id"], first["delivery_key"], first["claim_token"]
    )
    assert not await store.finish_coaching_delivery(
        user["user_id"], first["delivery_key"], first["claim_token"], "accepted"
    )


async def test_worker_default_deny_until_admission_readiness_reviewed(setup):
    store, channel, _, _, _, state = setup
    worker = CoachingDeliveryWorker(store, channel, clock=Clock(state))
    assert await worker.reconcile() == await worker.drain_once() == 0
    assert not store.proactive.reservations and not channel.sent


def test_follow_up_then_silence_including_weekly_review_until_reply():
    now = datetime(2026, 10, 22, 12, tzinfo=UTC)
    program = dict(
        program_id="p",
        state="active",
        timezone="UTC",
        check_in_days=list(range(1, 8)),
        check_in_time="12:00",
        starts_at=(now - timedelta(days=6)).isoformat(),
        ends_at=(now + timedelta(days=8)).isoformat(),
    )
    user = dict(wake_time="07:30", sleep_time="23:00")
    row = dict(
        local_day="2026-10-20",
        scheduled_at="2026-10-20T12:00:00Z",
        kind="check_in",
        state="accepted",
    )
    history = dict(last_reply_at=None, deliveries=[row])
    assert plan_coaching_delivery(program, user, now, history)["kind"] == "follow_up"
    history["deliveries"].append(
        {
            **row,
            "local_day": "2026-10-21",
            "scheduled_at": "2026-10-21T12:00:00Z",
            "kind": "follow_up",
        }
    )
    assert plan_coaching_delivery(program, user, now, history) is None
    history["last_reply_at"] = "2026-10-22T11:00:00Z"
    assert plan_coaching_delivery(program, user, now, history)["kind"] == "weekly_review"


@pytest.mark.parametrize(
    "now,wall,expected",
    [
        ("2026-03-08T07:30:00Z", "02:30", False),
        ("2026-11-01T05:30:00Z", "01:30", True),
        ("2026-11-01T06:30:00Z", "01:30", False),
    ],
)
def test_dst_nonexistent_skipped_and_earliest_fold_only(now, wall, expected):
    at = instant(now)
    program = dict(
        program_id="p",
        state="active",
        timezone="America/New_York",
        check_in_days=[7],
        check_in_time=wall,
        starts_at=(at - timedelta(days=1)).isoformat(),
        ends_at=(at + timedelta(days=2)).isoformat(),
    )
    assert (
        bool(
            plan_coaching_delivery(
                program,
                dict(wake_time="00:00", sleep_time="23:59"),
                at,
                dict(deliveries=[], last_reply_at=None),
            )
        )
        is expected
    )


@pytest.mark.parametrize("change", ["weekday", "quiet", "late"])
def test_unselected_days_quiet_hours_and_late_catchup_are_silent(change):
    now = datetime(2026, 10, 22, 12, tzinfo=UTC)
    program = dict(
        program_id="p",
        state="active",
        timezone="UTC",
        check_in_days=[4],
        check_in_time="12:00",
        starts_at=(now - timedelta(days=1)).isoformat(),
        ends_at=(now + timedelta(days=2)).isoformat(),
    )
    user = dict(wake_time="07:30", sleep_time="23:00")
    if change == "weekday":
        program["check_in_days"] = [1]
    elif change == "quiet":
        user["wake_time"] = "13:00"
    else:
        now += timedelta(minutes=16)
    assert (
        plan_coaching_delivery(program, user, now, dict(deliveries=[], last_reply_at=None)) is None
    )


@pytest.mark.parametrize("store_type", [FakeStore, InMemoryStore])
async def test_real_local_stores_isolate_scopes_require_policy_and_allow_withdrawal(store_type):
    store = store_type()
    user = await store.create_user(91901)
    other = await store.create_user(91902)
    assert not await store.has_coaching_consent(user["user_id"])
    await store.set_proactive_consent(
        user["user_id"], "reflect-v1", "reflect-sensitive-processing-v1", "ca"
    )
    assert not await store.has_coaching_consent(user["user_id"])
    row = await store.get_proactive_consent(user["user_id"], "reflect-v1")
    assert row["country_code"] == "CA"
    assert await store.get_proactive_consent(other["user_id"], "reflect-v1") is None
    await store.set_coaching_consent(user["user_id"], "unapproved-version")
    assert not await store.has_coaching_consent(user["user_id"])
    await store.set_coaching_consent(user["user_id"], "coaching-v1")
    assert await store.has_coaching_consent(user["user_id"])
    await store.set_coaching_consent(user["user_id"])
    assert not await store.has_coaching_consent(user["user_id"])


async def test_dispatch_rechecks_canonical_activation_evidence(setup):
    store, channel, user, _, worker, _ = setup
    await worker.reconcile()
    journey = store.activation_journeys[user["supabase_auth_id"]]
    reminder = next(
        row for row in store.reminders if row["reminder_id"] == journey["test_reminder_id"]
    )
    reminder.update(telegram_message_id=None, status="pending")
    assert not (await store.get_activation_state(user["supabase_auth_id"]))["completed"]
    assert await worker.drain_once() == 0
    assert not channel.sent


async def test_consumed_budget_survives_program_content_deletion(setup):
    store, _, user, program, worker, state = setup
    user["daily_message_budget"] = 1
    await worker.reconcile()
    assert await worker.drain_once() == 1
    await store.proactive.purge_programs(user["user_id"], [program["program_id"]])
    assert not store.proactive.deliveries
    row = next(iter(store.proactive.reservations.values()))
    assert row["program_id"] is None and row["state"] == "accepted"
    result = await store.proactive.reserve(user, "new-reminder", "recovery", state["now"])
    assert result["status"] == "budget_exhausted"


async def test_same_key_cannot_move_to_another_program(setup):
    store, _, user, _, _, state = setup
    await store.proactive.reserve(user, "same-key", "coaching", state["now"], "program-1")
    with pytest.raises(ValueError, match="different input"):
        await store.proactive.reserve(user, "same-key", "coaching", state["now"], "program-2")


async def test_deleting_program_releases_undispatched_standalone_reservation(setup):
    store, _, user, program, _, state = setup
    user["daily_message_budget"] = 1
    await store.proactive.reserve(
        user, "unused-coach", "coaching", state["now"], program["program_id"]
    )
    await store.proactive.purge_programs(user["user_id"], [program["program_id"]])
    old = store.proactive.reservations[user["user_id"], "unused-coach"]
    assert old["state"] == "cancelled" and old["program_id"] is None
    assert (await store.proactive.reserve(user, "new-reminder", "recovery", state["now"]))[
        "status"
    ] == "reserved"


@pytest.mark.parametrize("stage", ["history", "activation"])
async def test_kill_during_await_prevents_dispatch_and_releases_unused_slot(
    setup, monkeypatch, stage
):
    store, channel, _, _, worker, _ = setup
    assert await worker.reconcile() == 1
    name = "get_coaching_delivery_history" if stage == "history" else "get_activation_state"
    original = getattr(store, name)

    async def kill_during_read(*args):
        result = await original(*args)
        worker.admission_enabled = False
        return result

    monkeypatch.setattr(store, name, kill_during_read)
    assert await worker.drain_once() == 0
    assert not channel.sent
    assert next(iter(store.proactive.deliveries.values()))["state"] == "cancelled"
    assert next(iter(store.proactive.reservations.values()))["state"] == "cancelled"


async def test_readiness_callback_is_rechecked_after_activation_await(setup, monkeypatch):
    store, channel, _, _, worker, _ = setup
    await worker.reconcile()
    readiness = {"enabled": True}

    async def admitted():
        return readiness["enabled"]

    worker.admission_check = admitted
    original = store.get_activation_state

    async def withdraw_readiness(*args):
        result = await original(*args)
        readiness["enabled"] = False
        return result

    monkeypatch.setattr(store, "get_activation_state", withdraw_readiness)
    assert await worker.drain_once() == 0 and not channel.sent
    assert worker.admission_enabled is True
    assert next(iter(store.proactive.deliveries.values()))["state"] == "cancelled"


async def test_kill_after_durable_dispatch_keeps_uncertain_budget_without_send(setup, monkeypatch):
    store, channel, _, _, worker, state = setup
    await worker.reconcile()
    original = store.mark_coaching_dispatch

    async def kill_after_mark(*args):
        result = await original(*args)
        assert result is True
        worker.admission_enabled = False
        return result

    monkeypatch.setattr(store, "mark_coaching_dispatch", kill_after_mark)
    assert await worker.drain_once() == 0 and not channel.sent
    assert next(iter(store.proactive.deliveries.values()))["state"] == "uncertain"
    assert next(iter(store.proactive.reservations.values()))["state"] == "uncertain"
    worker.admission_enabled = True
    state["now"] += timedelta(minutes=6)
    assert await worker.drain_once() == 0 and not channel.sent


@pytest.mark.parametrize("kind", ["check_in", "follow_up", "weekly_review"])
async def test_delivery_buttons_bind_owned_program_and_current_version(setup, kind):
    import uuid

    store, channel, user, program, worker, state = setup
    if kind == "weekly_review":
        program["starts_at"] = (state["now"] - timedelta(days=6)).isoformat()
    elif kind == "follow_up":
        previous = state["now"] - timedelta(days=1)
        store.proactive.deliveries[user["user_id"], "prior"] = dict(
            user_id=user["user_id"],
            program_id=program["program_id"],
            delivery_key="prior",
            state="accepted",
            kind="check_in",
            local_day=previous.date().isoformat(),
            scheduled_at=previous.isoformat(),
            dispatched_at=previous.isoformat(),
        )
    await worker.reconcile()
    assert await worker.drain_once() == 1
    buttons = channel.sent[0]["buttons"][0]
    expected = (
        ["Continue", "Adjust", "Pause", "Stop"] if kind == "weekly_review" else ["Pause", "Stop"]
    )
    assert [button["text"] for button in buttons] == expected
    for button in buttons:
        prefix, action, identifier, version = button["callback_data"].split(":")
        assert prefix == "coach" and action == button["text"].lower()
        assert str(uuid.UUID(identifier)) == program["program_id"]
        assert int(version) == program["version"]
        assert len(button["callback_data"].encode()) <= 64


@pytest.mark.parametrize("hour, expected", [(8, False), (1, True)])
async def test_travel_quiet_hours_use_profile_zone_but_cadence_uses_program_zone(
    setup, hour, expected
):
    store, _, user, program, worker, state = setup
    state["now"] = state["now"].replace(hour=hour)
    program.update(check_in_time=f"{hour:02}:00", check_in_days=[4])
    user["timezone"] = "America/Los_Angeles"
    plan = plan_coaching_delivery(program, user, state["now"], {"deliveries": []})
    assert (plan is not None) is expected
    assert await worker.reconcile() == int(expected)
    if expected:
        assert plan["local_day"] == "2026-10-22"  # Profile date is still Wednesday.


@pytest.mark.parametrize("hour, expected", [(8, False), (1, True)])
async def test_dispatch_rechecks_quiet_window_after_profile_travel(setup, hour, expected):
    store, _, user, program, _, state = setup
    state["now"] = state["now"].replace(hour=hour)
    program.update(check_in_time=f"{hour:02}:00", check_in_days=[4])
    key = f"coach:{program['program_id']}:2026-10-22"
    result = await store.enqueue_coaching_delivery(
        user["user_id"], program["program_id"], 1, key, "2026-10-22", "check_in", state["now"]
    )
    assert result["status"] == "queued"
    claim = (await store.claim_coaching_deliveries("travel-worker"))[0]
    user["timezone"] = "America/Los_Angeles"
    assert (
        await store.mark_coaching_dispatch(user["user_id"], key, claim["claim_token"]) is expected
    )
    assert store.proactive.deliveries[user["user_id"], key]["state"] == (
        "dispatched" if expected else "cancelled"
    )


@pytest.mark.parametrize("state", ["reserved", "accepted", "uncertain"])
async def test_one_coach_per_profile_day_across_programs_and_deleted_program(setup, state):
    store, _, user, program, _, clock = setup
    first = await store.proactive.reserve(
        user, "coach:old", "coaching", clock["now"], program["program_id"]
    )
    assert first["status"] == "reserved"
    row = store.proactive.reservations[user["user_id"], "coach:old"]
    row.update(state=state, program_id=None)  # Deleted Program retains consumed daily capacity.
    second = await store.proactive.reserve(
        user, "coach:new", "coaching", clock["now"], "new-program"
    )
    assert second["status"] == "budget_exhausted"
    if state == "reserved":
        assert await store.proactive.release(user["user_id"], "coach:old")
        assert (
            await store.proactive.reserve(
                user, "coach:new", "coaching", clock["now"], "new-program"
            )
        )["status"] == "reserved"


@pytest.mark.parametrize("change", ["travel_collision", "budget_drop"])
async def test_dispatch_rechecks_profile_day_coach_cap_and_reduced_budget(setup, change):
    store, _, user, program, worker, state = setup
    assert await worker.reconcile() == 1
    claim = (await store.claim_coaching_deliveries("cap-worker"))[0]
    if change == "budget_drop":
        user["daily_message_budget"] = 0
    else:
        # Previously a distinct UTC day; now overlaps the current profile's local day.
        prior = state["now"] - timedelta(hours=13)
        assert (
            await store.proactive.reserve(user, "coach:prior", "coaching", prior, "old-program")
        )["status"] == "reserved"
        store.proactive.reservations[user["user_id"], "coach:prior"].update(
            state="accepted", program_id=None
        )
        user.update(timezone="Europe/Paris", wake_time="00:00", sleep_time="00:00")
    assert not await store.mark_coaching_dispatch(
        user["user_id"], claim["delivery_key"], claim["claim_token"]
    )
