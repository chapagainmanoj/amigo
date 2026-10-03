"""Shared Mode contracts; Supabase adapter uses a no-network RPC/query double, not live SQL.

Migration SQL assertions/concurrency probes independently certify actual PostgreSQL behavior.
The shared double verifies adapters and local mirrors without claiming to execute the SQL here.
Synchronous methods below implement the Supabase client's query-building protocol only.
"""

import asyncio
import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.memory.memory_store import InMemoryStore
from src.memory.store import MemoryStore
from tests.fakes import FakeStore


class _Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters = []

    def select(self, columns):
        self.columns = columns
        return self

    def eq(self, key, value):
        self.filters.append(("eq", key, value))
        return self

    def is_(self, key, value):
        assert value == "null"
        self.filters.append(("eq", key, None))
        return self

    def gt(self, key, value):
        self.filters.append(("gt", key, value))
        return self

    def maybe_single(self):
        return self

    async def execute(self):
        self.db.reads.append((self.table, self.filters))
        rows = (
            self.db.backing._sessions.values()
            if self.table == "sessions"
            else self.db.backing._mode_state.grants.values()
        )
        selected = []
        for row in rows:
            matches = True
            for operation, key, value in self.filters:
                if operation == "eq" and row.get(key) != value:
                    matches = False
                if operation == "gt" and datetime.fromisoformat(row[key]) <= datetime.fromisoformat(
                    value
                ):
                    matches = False
            if matches:
                selected.append(row)
        assert len(selected) <= 1
        return SimpleNamespace(data=copy.deepcopy(selected[0]) if selected else None)


class _RPC:
    def __init__(self, db, name, params):
        self.db, self.name, self.params = db, name, params

    async def execute(self):
        self.db.calls.append((self.name, self.params))
        p, store = self.params, self.db.backing
        if self.name == "grant_mode":
            expiry = datetime.fromisoformat(p["p_expires_at"]) if "p_expires_at" in p else None
            data = await store.grant_mode(
                p["p_user_id"], p["p_mode_id"], p["p_operator"], p["p_reason"], expiry
            )
        elif self.name == "revoke_mode_grant":
            data = await store.revoke_mode_grant(
                p["p_user_id"], p["p_mode_id"], p["p_operator"], p["p_reason"]
            )
        elif self.name == "set_active_mode":
            data = await store.set_active_mode(
                p["p_user_id"],
                p["p_session_id"],
                p["p_mode_id"],
                grant_required=p["p_grant_required"],
            )
        elif self.name == "create_mode_handoff":
            data = await store.create_handoff(
                p["p_user_id"],
                p["p_session_id"],
                p["p_source_mode_id"],
                p["p_target_mode_id"],
                p["p_carried_request"],
                source_grant_required=p["p_source_grant_required"],
                target_grant_required=p["p_target_grant_required"],
            )
        else:
            assert self.name == "resolve_mode_handoff"
            data = await store.resolve_handoff(
                p["p_user_id"], p["p_session_id"], p["p_handoff_id"], p["p_confirm"]
            )
        return SimpleNamespace(data=data)


class _Database:
    def __init__(self, backing):
        self.backing, self.calls, self.reads = backing, [], []

    def rpc(self, name, params):
        return _RPC(self, name, params)

    def table(self, name):
        assert name in {"sessions", "mode_grants"}
        return _Query(self, name)


@pytest.fixture(params=["local", "fake", "supabase-adapter"])
async def contract(request, monkeypatch):
    clock = {"now": datetime(2026, 10, 3, 12)}
    monkeypatch.setattr("src.memory.modes.utc_now", lambda: clock["now"])
    monkeypatch.setattr("src.memory.store.utc_now", lambda: clock["now"])
    backing = FakeStore() if request.param == "fake" else InMemoryStore()
    api = backing
    if request.param == "supabase-adapter":
        api = MemoryStore()
        api.db = _Database(backing)
    users = [await backing.create_user(91016000 + index) for index in range(8)]
    sessions = [await backing.create_session(user["user_id"]) for user in users]
    return SimpleNamespace(
        api=api,
        backing=backing,
        users=users,
        sessions=sessions,
        clock=clock,
        state=backing._mode_state,
    )


async def test_default_owned_session_and_atomic_entry(contract):
    c = contract
    user, other = (row["user_id"] for row in c.users[:2])
    session = c.sessions[0]["session_id"]
    assert await c.api.get_active_mode(user, session) is None
    assert await c.api.set_active_mode(other, session, "coach") == {"status": "unavailable"}
    assert await c.api.set_active_mode(user, session, "coach") == {"status": "unavailable"}
    await c.api.grant_mode(user, "coach", "operator", "trial")
    assert await c.api.set_active_mode(user, session, "coach") == {"status": "set"}
    assert await c.api.get_active_mode(other, session) is None
    assert await c.api.get_active_mode(user, session) == "coach"
    assert await c.api.set_active_mode(user, session, "daily") == {"status": "set"}
    assert await c.api.get_active_mode(user, session) is None
    assert await c.api.set_active_mode(user, session, "reflect", grant_required=False) == {
        "status": "set"
    }
    await c.backing.close_session(session)
    assert await c.api.get_active_mode(user, session) is None
    assert await c.api.set_active_mode(user, session, None) == {"status": "unavailable"}


async def test_concurrent_cap_duplicate_revoke_expiration_and_audit(contract):
    c = contract
    results = await asyncio.gather(
        *(c.api.grant_mode(user["user_id"], "coach", "operator", "trial") for user in c.users)
    )
    assert sum(result["status"] == "granted" for result in results) == 5
    assert sum(result["status"] == "cap_reached" for result in results) == 3
    user = c.users[0]["user_id"]
    duplicate = await c.api.grant_mode(user, "coach", "other-operator", "duplicate")
    assert duplicate["status"] == "already_active"
    assert duplicate["grant"]["grant_id"] == results[0]["grant"]["grant_id"]
    duplicate["grant"]["reason"] = "tampered"
    assert (await c.api.get_active_mode_grant(user, "coach"))["reason"] == "trial"
    assert await c.api.get_active_mode_grant(c.users[7]["user_id"], "coach") is None
    assert (await c.api.revoke_mode_grant(user, "coach", "operator-b", "stop"))[
        "status"
    ] == "revoked"
    assert await c.api.get_active_mode_grant(user, "coach") is None
    assert (await c.api.revoke_mode_grant(user, "coach", "operator-b", "stop"))[
        "status"
    ] == "not_active"
    assert (await c.api.grant_mode(c.users[5]["user_id"], "coach", "operator", "replace"))[
        "status"
    ] == "granted"
    c.clock["now"] += timedelta(days=14)
    assert await c.api.get_active_mode_grant(c.users[1]["user_id"], "coach") is None
    renewed = await c.api.grant_mode(c.users[1]["user_id"], "coach", "renewal-operator", "renew")
    assert renewed["status"] == "granted"
    expired = [event for event in c.state.events if event["action"] == "expired"]
    assert len(expired) == 5
    assert all(
        event["operator"] == "renewal-operator"
        and event["reason"] == "Expiry observed while granting: renew"
        for event in expired
    )


@pytest.mark.parametrize(
    "case", ["missing", "daily", "invalid_id", "operator", "reason", "past", "long"]
)
async def test_invalid_grants_write_nothing(contract, case):
    c = contract
    args = [c.users[0]["user_id"], "coach", "operator", "reason", None]
    replacements = {
        "missing": (0, "missing"),
        "daily": (1, "daily"),
        "invalid_id": (1, "bad mode"),
        "operator": (2, " "),
        "reason": (3, " "),
        "past": (4, c.clock["now"]),
        "long": (4, c.clock["now"] + timedelta(days=15)),
    }
    index, value = replacements[case]
    args[index] = value
    assert await c.api.grant_mode(*args) == {"status": "invalid"}
    assert c.state.grants == {} and c.state.events == []


async def test_confirmation_is_owned_atomic_single_use_and_detached(contract):
    c = contract
    user, other = (row["user_id"] for row in c.users[:2])
    session = c.sessions[0]["session_id"]
    await c.api.grant_mode(user, "coach", "operator", "trial")
    await c.api.set_active_mode(user, session, "coach")
    pending = await c.api.create_handoff(user, session, "coach", "daily", "Add buy milk")
    assert pending["status"] == "pending"
    handoff = pending["handoff"]
    assert datetime.fromisoformat(handoff["expires_at"]) - datetime.fromisoformat(
        handoff["created_at"]
    ) == timedelta(minutes=10)
    assert await c.api.resolve_handoff(other, session, handoff["handoff_id"], True) == {
        "status": "unavailable"
    }
    assert await c.api.resolve_handoff(
        user, c.sessions[1]["session_id"], handoff["handoff_id"], True
    ) == {"status": "unavailable"}
    handoff["carried_request"] = "tampered"
    results = await asyncio.gather(
        *(c.api.resolve_handoff(user, session, handoff["handoff_id"], True) for _ in range(4))
    )
    confirmed = [result for result in results if result["status"] == "confirmed"]
    assert len(confirmed) == 1
    assert sum(result == {"status": "unavailable"} for result in results) == 3
    assert confirmed[0]["handoff"]["carried_request"] == "Add buy milk"
    assert confirmed[0]["handoff"]["resolution"] == "confirmed"
    assert confirmed[0]["handoff"]["resolved_at"] is not None
    assert await c.api.get_active_mode(user, session) is None
    assert not (c.backing.tasks if isinstance(c.backing, FakeStore) else c.backing._tasks)


@pytest.mark.parametrize(
    "case,status",
    [
        ("decline", "declined"),
        ("expired", "expired"),
        ("closed", "unavailable"),
        ("changed", "unavailable"),
        ("revoked", "unavailable"),
        ("grant_expired", "unavailable"),
    ],
)
async def test_nonconfirmations_never_return_carried_request_or_switch(contract, case, status):
    c = contract
    user, session = c.users[0]["user_id"], c.sessions[0]["session_id"]
    await c.api.grant_mode(
        user, "coach", "operator", "short trial", c.clock["now"] + timedelta(minutes=1)
    )
    await c.api.set_active_mode(user, session, "coach")
    pending = await c.api.create_handoff(
        user, session, "coach", "daily", "private carried sentinel"
    )
    handoff_id = pending["handoff"]["handoff_id"]
    if case == "expired":
        c.clock["now"] += timedelta(minutes=10)
    elif case == "grant_expired":
        c.clock["now"] += timedelta(minutes=1)
    elif case == "closed":
        await c.backing.close_session(session)
    elif case == "changed":
        await c.api.set_active_mode(user, session, "reflect", grant_required=False)
    elif case == "revoked":
        await c.api.revoke_mode_grant(user, "coach", "operator", "withdraw")
    before = await c.api.get_active_mode(user, session)
    assert await c.api.resolve_handoff(user, session, handoff_id, case != "decline") == {
        "status": status
    }
    assert await c.api.get_active_mode(user, session) == before
    assert await c.api.resolve_handoff(user, session, handoff_id, True) == {"status": "unavailable"}


async def test_handoff_stored_trusted_flags_and_target_grant_recheck(contract):
    c = contract
    user, session = c.users[0]["user_id"], c.sessions[0]["session_id"]
    await c.api.set_active_mode(user, session, "journal", grant_required=False)
    pending = await c.api.create_handoff(
        user,
        session,
        "journal",
        "reflect",
        "Selected takeaway",
        source_grant_required=False,
        target_grant_required=False,
    )
    assert pending["handoff"]["source_grant_required"] is False
    assert pending["handoff"]["target_grant_required"] is False
    assert (await c.api.resolve_handoff(user, session, pending["handoff"]["handoff_id"], True))[
        "status"
    ] == "confirmed"
    await c.api.set_active_mode(user, session, "daily")
    await c.api.grant_mode(user, "coach", "operator", "trial")
    pending = await c.api.create_handoff(user, session, "daily", "coach", "Selected request")
    await c.api.revoke_mode_grant(user, "coach", "operator", "withdraw")
    assert await c.api.resolve_handoff(user, session, pending["handoff"]["handoff_id"], True) == {
        "status": "unavailable"
    }


async def test_adapter_rpc_parameters_and_owned_read_filters():
    backing = InMemoryStore()
    user = await backing.create_user(1)
    session = await backing.create_session(user["user_id"])
    store = MemoryStore()
    store.db = _Database(backing)
    await store.grant_mode(user["user_id"], "coach", "operator", "reason")
    assert store.db.calls[-1] == (
        "grant_mode",
        {
            "p_user_id": user["user_id"],
            "p_mode_id": "coach",
            "p_operator": "operator",
            "p_reason": "reason",
        },
    )
    expiry = datetime.now(UTC) + timedelta(days=1)
    await store.grant_mode(user["user_id"], "reflect", "operator", "reason", expiry)
    assert store.db.calls[-1][1]["p_expires_at"] == expiry.isoformat()
    await store.get_active_mode(user["user_id"], session["session_id"])
    assert store.db.reads[-1] == (
        "sessions",
        [
            ("eq", "user_id", user["user_id"]),
            ("eq", "session_id", session["session_id"]),
            ("eq", "ended_at", None),
        ],
    )
    await store.get_active_mode_grant(user["user_id"], "coach")
    filters = store.db.reads[-1][1]
    assert filters[:3] == [
        ("eq", "user_id", user["user_id"]),
        ("eq", "mode_id", "coach"),
        ("eq", "revoked_at", None),
    ]
    assert filters[3][0:2] == ("gt", "expires_at")


@pytest.mark.parametrize("expired", [False, True])
async def test_decline_priority_matches_sql_after_withdrawal(contract, expired):
    c = contract
    user, session = c.users[0]["user_id"], c.sessions[0]["session_id"]
    await c.api.grant_mode(user, "coach", "operator", "trial")
    await c.api.set_active_mode(user, session, "coach")
    pending = await c.api.create_handoff(user, session, "coach", "daily", "No side effects")
    await c.api.revoke_mode_grant(user, "coach", "operator", "withdraw")
    await c.backing.close_session(session)
    if expired:
        c.clock["now"] += timedelta(minutes=10)
    expected = "expired" if expired else "declined"
    result = await c.api.resolve_handoff(user, session, pending["handoff"]["handoff_id"], False)
    assert result == {"status": expected}


async def test_invalid_handoffs_and_null_trusted_flags_are_refused(contract):
    c = contract
    user, session = c.users[0]["user_id"], c.sessions[0]["session_id"]
    assert await c.api.set_active_mode(user, session, "coach", grant_required=None) == {
        "status": "invalid"
    }
    for source, target, text in (
        ("daily", "daily", "text"),
        ("daily", "bad mode", "text"),
        ("daily", "coach", " "),
    ):
        assert await c.api.create_handoff(user, session, source, target, text) == {
            "status": "invalid"
        }
    assert await c.api.create_handoff(
        user, session, "daily", "coach", "text", target_grant_required=None
    ) == {"status": "invalid"}
    assert await c.api.resolve_handoff(user, session, "missing", None) == {"status": "invalid"}
    assert await c.api.create_handoff(c.users[1]["user_id"], session, "daily", "coach", "text") == {
        "status": "unavailable"
    }
    assert c.state.handoffs == {}


async def test_revoked_entry_and_returned_flag_tampering_cannot_authorize_confirmation(contract):
    c = contract
    user, session = c.users[0]["user_id"], c.sessions[0]["session_id"]
    await c.api.grant_mode(user, "coach", "operator", "trial")
    await c.api.set_active_mode(user, session, "coach")
    pending = await c.api.create_handoff(user, session, "coach", "daily", "Selected request")
    pending["handoff"]["source_grant_required"] = False
    await c.api.revoke_mode_grant(user, "coach", "operator", "withdraw")
    assert await c.api.set_active_mode(user, session, "coach") == {"status": "unavailable"}
    assert await c.api.resolve_handoff(user, session, pending["handoff"]["handoff_id"], True) == {
        "status": "unavailable"
    }


async def test_expiry_revalidated_after_local_lock_wait(contract):
    c = contract
    expiry = c.clock["now"] + timedelta(seconds=1)
    await c.state.lock.acquire()
    try:
        pending = asyncio.create_task(
            c.api.grant_mode(c.users[0]["user_id"], "coach", "op", "trial", expiry)
        )
        await asyncio.sleep(0)  # Give the request a chance to reach the held serialization lock.
        c.clock["now"] += timedelta(seconds=2)
    finally:
        c.state.lock.release()
    assert await pending == {"status": "invalid"}
    assert c.state.grants == {} and c.state.events == []
