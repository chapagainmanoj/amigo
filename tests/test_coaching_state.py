"""Isolated Coaching Program lifecycle; no scheduler, production Store or provider wiring."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from src.commands.base import IdempotencyConflictError, InvalidTransitionError, StaleVersionError
from src.memory.coaching import LocalCoachingState


@pytest.fixture
async def state(monkeypatch):
    clock = {"now": datetime(2026, 10, 22, 12)}
    monkeypatch.setattr("src.memory.coaching.utc_now", lambda: clock["now"])
    return LocalCoachingState(), clock


async def draft(api, user="owner", key="draft"):
    return await api.draft(
        user,
        key,
        key,
        goal="Walk outside",
        success_measure="I choose 3 walks",
        check_in_days=[5, 1],
        check_in_time="18:00",
        timezone="Asia/Kathmandu",
    )


async def active(api):
    result = await draft(api)
    program = result["program"]
    token = await api.issue_approval("owner", program["program_id"], 1)
    return await api.confirm("owner", token, "confirm", "confirm")


async def test_draft_needs_current_participant_token_then_starts_fourteen_day_term(state):
    api, clock = state
    result = await draft(api)
    row = result["program"]
    assert row["state"] == "draft" and row["starts_at"] is None
    assert row["check_in_days"] == [1, 5]
    with pytest.raises(InvalidTransitionError):
        await api.change("owner", row["program_id"], 1, "activate", "a", "a")
    assert (await api.get("owner"))["version"] == 1
    token = await api.issue_approval("owner", row["program_id"], 1)
    with pytest.raises(ValueError):
        await api.confirm("other", token, "a", "a")
    result = await api.confirm("owner", token, "confirm", "confirm")
    assert result["program"]["state"] == "active"
    assert datetime.fromisoformat(result["program"]["starts_at"]) == clock["now"].replace(
        tzinfo=UTC
    )
    assert datetime.fromisoformat(result["program"]["ends_at"]) - datetime.fromisoformat(
        result["program"]["starts_at"]
    ) == timedelta(days=14)
    assert await api.confirm("owner", token, "confirm", "confirm") == result
    with pytest.raises(IdempotencyConflictError):
        await api.confirm("owner", token, "confirm", "changed")
    with pytest.raises(StaleVersionError):
        await api.confirm("owner", token, "another", "another")


async def test_one_nonterminal_program_includes_drafts_and_is_atomic(state):
    api, _ = state
    results = await asyncio.gather(draft(api, key="a"), draft(api, key="b"), return_exceptions=True)
    assert sum(isinstance(item, dict) for item in results) == 1
    assert sum(isinstance(item, InvalidTransitionError) for item in results) == 1
    owner = await api.get("owner")
    assert await api.get("other", owner["program_id"]) is None
    with pytest.raises(ValueError):
        await api.change("other", owner["program_id"], 1, "stop", "x", "x")


async def test_revision_invalidates_issued_summary_approval(state):
    api, _ = state
    row = (await draft(api))["program"]
    token = await api.issue_approval("owner", row["program_id"], 1)
    await api.revise(
        "owner",
        row["program_id"],
        1,
        "revise",
        "revise",
        goal="Read",
        success_measure="My own measure",
        check_in_days=[2],
        check_in_time="17:00",
        timezone="UTC",
    )
    with pytest.raises(StaleVersionError):
        await api.confirm("owner", token, "confirm", "confirm")
    assert (await api.get("owner"))["state"] == "draft"


async def test_approval_expires_at_exact_ten_minutes(state):
    api, clock = state
    row = (await draft(api))["program"]
    token = await api.issue_approval("owner", row["program_id"], 1)
    clock["now"] += timedelta(minutes=10)
    with pytest.raises(InvalidTransitionError):
        await api.confirm("owner", token, "confirm", "confirm")
    assert (await api.get("owner"))["version"] == 1


@pytest.mark.parametrize("days", [None, 0, 15, True, 1.5])
async def test_extension_requires_explicit_bounded_integer_days(state, days):
    api, _ = state
    row = (await active(api))["program"]
    with pytest.raises(ValueError):
        await api.change(
            "owner", row["program_id"], row["version"], "extend", "x", "x", extension_days=days
        )
    assert (await api.get("owner"))["version"] == row["version"]


async def test_weekly_continue_never_extends_adjust_pauses_and_revision_preserves_term(state):
    api, _ = state
    row = (await active(api))["program"]
    result = await api.change(
        "owner",
        row["program_id"],
        row["version"],
        "record_weekly_choice",
        "weekly",
        "weekly",
        weekly_choice="continue",
    )
    assert result["program"]["ends_at"] == row["ends_at"]
    result = await api.change(
        "owner",
        row["program_id"],
        result["program"]["version"],
        "record_weekly_choice",
        "adjust",
        "adjust",
        weekly_choice="adjust",
    )
    assert result["program"]["state"] == "paused"
    result = await api.revise(
        "owner",
        row["program_id"],
        result["program"]["version"],
        "r",
        "r",
        goal="Revised goal",
        success_measure="Participant measure",
        check_in_days=[1],
        check_in_time="12:00",
        timezone="UTC",
    )
    token = await api.issue_approval("owner", row["program_id"], result["program"]["version"])
    revised = await api.confirm("owner", token, "approved-revision", "approved-revision")
    assert revised["program"]["ends_at"] == row["ends_at"]
    assert revised["program"]["starts_at"] == row["starts_at"]


async def test_versioned_progress_pause_resume_extend_stop_and_replay(state):
    api, _ = state
    row = (await active(api))["program"]
    for action, fields in [
        ("record_progress", {"progress_text": "I chose one walk."}),
        ("pause", {}),
        ("resume", {}),
        ("extend", {"extension_days": 2}),
        ("stop", {}),
    ]:
        old_version = row["version"]
        result = await api.change(
            "owner", row["program_id"], old_version, action, action, action, **fields
        )
        assert (
            await api.change(
                "owner", row["program_id"], old_version, action, action, action, **fields
            )
            == result
        )
        row = result["program"]
        assert row["version"] == old_version + 1
    assert row["state"] == "stopped" and row["extended_count"] == 1
    assert (await api.list_entries("owner", row["program_id"]))[2][
        "participant_text"
    ] == "I chose one walk."
    with pytest.raises(InvalidTransitionError):
        await api.change("owner", row["program_id"], row["version"], "resume", "late", "late")
    assert (await draft(api, key="new"))["program"]["state"] == "draft"


async def test_paused_program_completes_at_fixed_term_and_does_not_extend_on_silence(state):
    api, clock = state
    row = (await active(api))["program"]
    await api.change("owner", row["program_id"], row["version"], "pause", "pause", "pause")
    clock["now"] += timedelta(days=14)
    assert await api.complete_due() == [{"program_id": row["program_id"], "user_id": "owner"}]
    assert await api.complete_due() == []
    assert await api.get("owner") is None
    assert (await api.get("owner", row["program_id"]))["state"] == "completed"


async def test_export_and_delete_owned_content_tokens_and_receipts_are_isolated(state):
    api, _ = state
    row = (await draft(api))["program"]
    await api.issue_approval("owner", row["program_id"], 1)
    await draft(api, user="other")
    exported = await api.export("owner")
    assert len(exported["programs"]) == len(exported["entries"]) == 1
    assert "approvals" not in exported
    exported["programs"][0]["goal"] = "tamper"
    assert (await api.get("owner"))["goal"] == "Walk outside"
    await api.delete("owner")
    assert await api.export("owner") == {"programs": [], "entries": []}
    assert all(key[0] != "owner" for key in api.receipts)
    assert not api.approvals
    assert (await api.get("other"))["goal"] == "Walk outside"


@pytest.mark.parametrize(
    "days,time,timezone",
    [
        ([0], "12:00", "UTC"),
        ([1, 1], "12:00", "UTC"),
        ([True], "12:00", "UTC"),
        ([1], "12:00:01", "UTC"),
        ([1], "0830", "UTC"),
        ([1], "08:30:00", "UTC"),
        ([1], "12:00+01:00", "UTC"),
        ([1], "12:00", "Unknown/Zone"),
    ],
)
async def test_invalid_program_configuration_never_writes(state, days, time, timezone):
    api, _ = state
    with pytest.raises(ValueError):
        await api.draft(
            "owner",
            "x",
            "x",
            goal="Goal",
            success_measure="Own measure",
            check_in_days=days,
            check_in_time=time,
            timezone=timezone,
        )
    assert not api.programs and not api.entries and not api.receipts
