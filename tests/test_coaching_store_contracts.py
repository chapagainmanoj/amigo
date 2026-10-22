"""Shared coaching mutation/rights contracts; Supabase uses a no-network RPC adapter double."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.commands.base import InvalidTransitionError, StaleVersionError
from src.memory.memory_store import InMemoryStore
from src.memory.store import MemoryStore
from tests.fakes import FakeStore


class RPCDatabase:
    """SDK-compatible synchronous builder; dispatch itself remains asynchronous."""

    def __init__(self, backing):
        self.backing = backing
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return SimpleNamespace(execute=lambda: self.execute(name, params))

    async def execute(self, name, params):
        p, store = params, self.backing
        if name == "coaching_program_command":
            args = (p["p_user_id"], p["p_idempotency_key"], p["p_payload_hash"])
            data = p["p_data"]
            if p["p_action"] == "draft":
                result = await store.draft_coaching_program(*args, **data)
            elif p["p_action"] == "revise":
                result = await store.revise_coaching_draft(
                    p["p_user_id"],
                    p["p_program_id"],
                    p["p_expected_version"],
                    p["p_idempotency_key"],
                    p["p_payload_hash"],
                    **data,
                )
            else:
                result = await store.change_coaching_program(
                    p["p_user_id"],
                    p["p_program_id"],
                    p["p_expected_version"],
                    p["p_action"],
                    p["p_idempotency_key"],
                    p["p_payload_hash"],
                    **data,
                )
        elif name == "issue_coaching_approval":
            result = await store.issue_coaching_approval(
                p["p_user_id"],
                p["p_program_id"],
                p["p_expected_version"],
            )
        elif name == "confirm_coaching_approval":
            result = await store.confirm_coaching_approval(
                p["p_user_id"],
                p["p_token"],
                p["p_idempotency_key"],
                p["p_payload_hash"],
            )
        elif name == "export_coaching_data":
            result = await store.export_coaching_data(p["p_user_id"])
        elif name == "delete_coaching_data":
            result = await store.delete_coaching_data(p["p_user_id"], p["p_verified_request_id"])
        else:
            assert name == "complete_due_coaching_programs"
            result = await store.complete_due_coaching_programs()
        return SimpleNamespace(data=result)


@pytest.fixture(params=["memory", "fake", "supabase-adapter"])
async def contract(request):
    backing = FakeStore() if request.param == "fake" else InMemoryStore()
    user = await backing.create_user(18001)
    other = await backing.create_user(18002)
    api = backing
    if request.param == "supabase-adapter":
        api = MemoryStore()
        api.db = RPCDatabase(backing)
    return api, user["user_id"], other["user_id"]


async def draft(api, user, key="draft"):
    return await api.draft_coaching_program(
        user,
        key,
        key,
        goal="Walk outside",
        success_measure="I choose three walks",
        check_in_days=[1, 5],
        check_in_time="18:00",
        timezone="UTC",
    )


async def test_owned_versioned_approval_lifecycle_and_rights(contract):
    api, user, other = contract
    result = await draft(api, user)
    program = result["program"]
    assert await draft(api, user) == result
    with pytest.raises(InvalidTransitionError):
        await draft(api, user, "another")
    with pytest.raises(ValueError):
        await api.issue_coaching_approval(other, program["program_id"], 1)
    token = await api.issue_coaching_approval(user, program["program_id"], 1)
    result = await api.confirm_coaching_approval(user, token, "confirm", "confirm")
    assert result["program"]["state"] == "active"
    assert await api.confirm_coaching_approval(user, token, "confirm", "confirm") == result
    with pytest.raises(StaleVersionError):
        await api.change_coaching_program(user, program["program_id"], 1, "stop", "stale", "stale")
    result = await api.change_coaching_program(
        user,
        program["program_id"],
        2,
        "record_progress",
        "progress",
        "progress",
        progress_text="I chose one walk.",
    )
    assert result["entry"]["participant_text"] == "I chose one walk."
    await draft(api, other)
    export = await api.export_coaching_data(user)
    assert len(export["programs"]) == 1
    assert len(export["entries"]) == 3
    with pytest.raises(ValueError):
        await api.delete_coaching_data(user, "")
    await api.delete_coaching_data(user, "verified-request")
    assert await api.export_coaching_data(user) == {"programs": [], "entries": []}
    assert len((await api.export_coaching_data(other))["programs"]) == 1


async def test_revision_is_draft_and_requires_new_approval(contract):
    api, user, _ = contract
    row = (await draft(api, user))["program"]
    old_token = await api.issue_coaching_approval(user, row["program_id"], 1)
    result = await api.revise_coaching_draft(
        user,
        row["program_id"],
        1,
        "revise",
        "revise",
        goal="Read outside",
        success_measure="My chosen measure",
        check_in_days=[2],
        check_in_time="17:00",
        timezone="UTC",
    )
    assert result["program"]["state"] == "draft" and result["program"]["version"] == 2
    with pytest.raises(StaleVersionError):
        await api.confirm_coaching_approval(user, old_token, "old", "old")
    token = await api.issue_coaching_approval(user, row["program_id"], 2)
    assert (await api.confirm_coaching_approval(user, token, "new", "new"))["program"][
        "state"
    ] == "active"


async def test_coaching_rpc_draft_and_confirmation_parameter_contract():
    api = MemoryStore()
    query = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(data="opaque")))
    api.db = SimpleNamespace(rpc=Mock(return_value=query))
    await draft(api, "owner")
    name, params = api.db.rpc.call_args.args
    assert name == "coaching_program_command"
    assert params["p_user_id"] == "owner" and params["p_program_id"] is None
    assert params["p_action"] == "draft" and params["p_expected_version"] is None
    await api.confirm_coaching_approval("owner", "opaque-token", "confirm", "hash")
    api.db.rpc.assert_called_with(
        "confirm_coaching_approval",
        {
            "p_user_id": "owner",
            "p_token": "opaque-token",
            "p_idempotency_key": "confirm",
            "p_payload_hash": "hash",
        },
    )


async def test_coaching_read_queries_filter_owner_and_program():
    api = MemoryStore()
    query = Mock()
    for method in ["select", "eq", "in_", "order", "limit", "maybe_single"]:
        getattr(query, method).return_value = query
    query.execute = AsyncMock(return_value=SimpleNamespace(data={"program_id": "program"}))
    api.db = SimpleNamespace(table=Mock(return_value=query))
    await api.get_coaching_program("owner", "program")
    query.eq.assert_any_call("user_id", "owner")
    query.eq.assert_any_call("program_id", "program")
    query.reset_mock()
    await api.get_coaching_program("owner")
    query.eq.assert_any_call("user_id", "owner")
    query.in_.assert_called_with("state", ["draft", "active", "paused"])
