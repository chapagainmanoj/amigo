"""Owner-only, synthetic SQL probes; run exclusively against an isolated proposal database."""

import argparse
import concurrent.futures
import json
import re
import subprocess
import uuid
from pathlib import Path

PSQL = "/opt/homebrew/opt/postgresql@15/bin/psql"
ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    base = [PSQL, "-X", "-At", "-v", "ON_ERROR_STOP=1", "-h", args.host,
            "-p", args.port, "-U", "mano", "-d", args.database]

    def query(sql, *, allow_error=False):
        result = subprocess.run(base + ["-c", "SET statement_timeout='10s'; " + sql],
                                text=True, capture_output=True, timeout=15)
        if result.returncode and not allow_error:
            raise AssertionError(result.stderr)
        return result

    def value(sql):
        lines = [line for line in query(sql).stdout.strip().splitlines()
                 if not re.fullmatch(r"(?:SET|INSERT \d+ \d+|UPDATE \d+|DELETE \d+)", line)]
        return lines[-1]

    def rpc(sql):
        return json.loads(value("SET ROLE service_role; SELECT " + sql))

    def gate(sql):
        process = subprocess.Popen(base + ["-c", "BEGIN; " + sql +
                                   "; SELECT 'GATE_READY'; SELECT pg_sleep(1.2); COMMIT;"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        while True:
            line = process.stdout.readline()
            if "GATE_READY" in line:
                return process
            if not line:
                raise AssertionError(process.stderr.read())

    def release(process):
        _, errors = process.communicate(timeout=10)
        assert process.returncode == 0, errors

    prefix = uuid.uuid4().hex[:10]
    mode = "probe_" + prefix
    chat_base = 940000000 + int(prefix[:6], 16)
    users = []
    sessions = []
    tokens = []
    original = query("SELECT pg_get_functiondef('public.complete_pairing(text,bigint)'::regprocedure)").stdout
    original = original.removeprefix("SET\n").strip()
    results = {}
    try:
        assert value("SELECT get_app_schema_version()") == "16"
        query((Path(__file__).with_name("assert_016_session_modes_grants_handoffs.sql")).read_text())
        results["016_rollback_assertions"] = "passed"
        for index in range(8):
            users.append(value(f"INSERT INTO user_profiles(telegram_chat_id) VALUES({chat_base + index}) RETURNING user_id"))
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            grants = list(pool.map(lambda user: rpc(f"grant_mode('{user}', '{mode}', 'probe', 'capacity')")["status"], users))
        assert grants.count("granted") == 5 and grants.count("cap_reached") == 3, grants
        results["concurrent_capacity"] = grants
        user = next(user for user in users if value(f"SELECT EXISTS(SELECT 1 FROM mode_grants WHERE user_id='{user}' AND mode_id='{mode}')") == "t")
        session = value(f"INSERT INTO sessions(user_id) VALUES('{user}') RETURNING session_id")
        sessions.append(session)

        def enter():
            assert rpc(f"set_active_mode('{user}', '{session}', '{mode}', TRUE)")["status"] == "set"

        def proposal():
            result = rpc(f"create_mode_handoff('{user}', '{session}', '{mode}', 'daily', 'synthetic request', TRUE, FALSE)")
            assert result["status"] == "pending", result
            return result["handoff"]["handoff_id"]

        enter()
        handoff = proposal()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            confirmations = list(pool.map(lambda _: rpc(f"resolve_mode_handoff('{user}', '{session}', '{handoff}', TRUE)")["status"], range(4)))
        assert confirmations.count("confirmed") == 1 and confirmations.count("unavailable") == 3, confirmations
        assert value(f"SELECT active_mode_id IS NULL FROM sessions WHERE session_id='{session}'") == "t"
        results["simultaneous_confirmation"] = confirmations

        enter()
        handoff = proposal()
        query(f"UPDATE mode_handoffs SET expires_at=clock_timestamp()+interval '0.2 seconds' WHERE handoff_id='{handoff}'")
        blocker = gate(f"SELECT 1 FROM sessions WHERE session_id='{session}' FOR UPDATE")
        status = rpc(f"resolve_mode_handoff('{user}', '{session}', '{handoff}', TRUE)")["status"]
        release(blocker)
        assert status == "expired", status
        results["handoff_expiry_after_session_wait"] = status

        handoff = proposal()
        query(f"UPDATE mode_grants SET expires_at=clock_timestamp()+interval '0.2 seconds' WHERE user_id='{user}' AND mode_id='{mode}'")
        blocker = gate(f"SELECT 1 FROM sessions WHERE session_id='{session}' FOR UPDATE")
        status = rpc(f"resolve_mode_handoff('{user}', '{session}', '{handoff}', TRUE)")["status"]
        release(blocker)
        assert status == "unavailable", status
        results["grant_expiry_after_session_wait"] = status

        assert rpc(f"grant_mode('{user}', '{mode}', 'probe', 'renew')")["status"] == "granted"
        assert rpc(f"set_active_mode('{user}', '{session}', 'daily', FALSE)")["status"] == "set"
        blocker = gate(f"SELECT revoke_mode_grant('{user}', '{mode}', 'probe', 'concurrent revoke')")
        status = rpc(f"set_active_mode('{user}', '{session}', '{mode}', TRUE)")["status"]
        release(blocker)
        assert status == "unavailable", status
        results["entry_after_concurrent_revoke"] = status

        # Inject an observational gate after the first identity-row lock. Original003 reaches
        # the gate in both crossed calls; ordered015 serializes at the lower UUID before it.
        auths = [str(uuid.uuid4()), str(uuid.uuid4())]
        pair_users = []
        for index, auth in enumerate(auths):
            pair_users.append(value(f"INSERT INTO user_profiles(telegram_chat_id,supabase_auth_id) VALUES({chat_base + 20 + index},'{auth}') RETURNING user_id"))
        users.extend(pair_users)
        for auth in auths:
            token = uuid.uuid4().hex
            tokens.append(token)
            query(f"INSERT INTO pairing_tokens(token,supabase_auth_id,expires_at) VALUES('{token}','{auth}',clock_timestamp()+interval '5 minutes')")
        baseline = re.search(r"CREATE OR REPLACE FUNCTION public.complete_pairing\(.*?\n\$\$;", (ROOT / 'migrations/003_secure_pairing_tokens.sql').read_text(), re.S).group()
        gate_key = 160150016
        injected = f"\n  PERFORM pg_advisory_xact_lock({gate_key});"
        for name, definition, anchor in [
            ("003_before", baseline, "v_chat_exists := FOUND;"),
            ("015_after", original, "PERFORM 1 FROM public.user_profiles WHERE user_id = v_candidate_user_id FOR UPDATE;"),
        ]:
            assert definition.count(anchor) == 1
            query(definition.replace(anchor, anchor + injected))
            blocker = gate(f"SELECT pg_advisory_xact_lock({gate_key})")
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                calls = list(pool.map(lambda index: query(f"SET ROLE service_role; SELECT complete_pairing('{tokens[1-index]}',{chat_base + 20 + index})", allow_error=True), range(2)))
            release(blocker)
            deadlocks = sum("deadlock detected" in result.stderr for result in calls)
            assert deadlocks == (1 if name == "003_before" else 0), [r.stderr for r in calls]
            if name == "015_after":
                assert all('"status": "conflict"' in r.stdout for r in calls)
            results[name + "_crossed_pairing_deadlocks"] = deadlocks
        print(json.dumps(results, sort_keys=True))
    finally:
        query(original)
        ids = ",".join("'" + user + "'" for user in users)
        if ids:
            query(f"DELETE FROM mode_handoffs WHERE user_id IN({ids}); DELETE FROM mode_grant_events WHERE user_id IN({ids}); DELETE FROM mode_grants WHERE user_id IN({ids}); DELETE FROM sessions WHERE user_id IN({ids}); DELETE FROM user_profiles WHERE user_id IN({ids})")
        if tokens:
            query("DELETE FROM pairing_tokens WHERE token IN(" + ",".join("'" + token + "'" for token in tokens) + ")")


if __name__ == "__main__":
    main()
