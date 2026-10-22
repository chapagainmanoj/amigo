"""Isolated local-PostgreSQL probe for 017 backfill and fenced handoff recovery.

Creates one fresh uniquely named database through the supplied temporary Unix socket.
Never modifies the caller's PGDATABASE, never loads .env, and retains the new database
for inspection. This probes claim concurrency and replay state, not Tool exactly-once effects.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(database: str, env: dict[str, str], *arguments: str) -> str:
    result = subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-q", "-t", "-A", "-d", database, *arguments],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def main() -> None:
    env = dict(os.environ)
    if not env.get("PGHOST", "").startswith(("/private/tmp/", "/tmp/")):
        raise SystemExit("PGHOST must identify a temporary local Unix socket directory")
    env.pop("PGOPTIONS", None)
    env.pop("PGDATABASE", None)
    database = "amigo017_verify_" + uuid.uuid4().hex[:12]
    _run("postgres", env, "-c", f"CREATE DATABASE {database}")
    print(f"database: {database}")
    chain = [ROOT / "tests/sql/bootstrap_supabase_roles.sql"] + [
        path
        for path in sorted((ROOT / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
        if int(path.name[:3]) <= 16
    ]
    arguments = [argument for path in chain for argument in ("-f", str(path))]
    _run(database, env, *arguments)
    user, source, target = (str(uuid.uuid4()) for _ in range(3))
    _run(
        database,
        env,
        "-c",
        f"""
        INSERT INTO public.user_profiles(user_id, telegram_chat_id)
          VALUES ('{user}', 910179999);
        INSERT INTO public.sessions(session_id, user_id, active_mode_id)
          VALUES ('{source}', '{user}', 'coach'), ('{target}', '{user}', NULL);
    """,
    )
    _run(database, env, "-f", str(ROOT / "migrations/017_mode_conversations.sql"))
    backfill = json.loads(
        _run(
            database,
            env,
            "-c",
            f"""
        SELECT json_build_object(
          'coach', (SELECT mode_id FROM public.sessions WHERE session_id='{source}'),
          'daily', (SELECT mode_id FROM public.sessions WHERE session_id='{target}'),
          'schema', public.get_app_schema_version());
    """,
        )
    )
    assert backfill == {"coach": "coach", "daily": "daily", "schema": 17}, backfill
    print("PASS: 016 existing coach/null-active Sessions backfill coach/daily; schema=17")
    proposal = json.loads(
        _run(
            database,
            env,
            "-c",
            f"""
        SELECT public.create_mode_handoff('{user}', '{source}', 'coach', 'daily',
          'Synthetic execution probe', FALSE, FALSE);
    """,
        )
    )
    handoff = proposal["handoff"]["handoff_id"]
    resolved = json.loads(
        _run(
            database,
            env,
            "-c",
            f"""
        SELECT public.resolve_mode_handoff('{user}', '{source}', '{handoff}', TRUE);
    """,
        )
    )
    assert resolved["status"] == "confirmed", resolved["status"]
    barrier = threading.Barrier(8)

    def claim(index: int) -> dict:
        barrier.wait(timeout=10)
        return json.loads(
            _run(
                database,
                env,
                "-c",
                f"""
            SELECT public.claim_handoff_execution(
              '{user}', '{handoff}', 'worker-{index}', '{target}');
        """,
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(claim, range(8)))
    statuses = [response["status"] for response in responses]
    assert statuses.count("claimed") == 1 and statuses.count("busy") == 7, statuses
    first = next(response["handoff"] for response in responses if response["status"] == "claimed")
    old_token = first["execution_claim_token"]
    plan = '[{"ordinal":1,"kind":"synthetic"}]'
    saved = _run(
        database,
        env,
        "-c",
        f"""
        SELECT public.save_handoff_execution_plan('{user}', '{handoff}', '{old_token}', '{plan}');
    """,
    )
    assert saved == "t", saved
    print("PASS: 8 concurrent claim RPCs => 1 claimed, 7 busy; replay plan persisted")
    _run(
        database,
        env,
        "-c",
        f"""
        UPDATE public.mode_handoffs SET execution_claimed_at=clock_timestamp()-interval '6 minutes'
          WHERE handoff_id='{handoff}';
        UPDATE public.sessions SET ended_at=clock_timestamp() WHERE session_id='{target}';
    """,
    )
    expired = _run(
        database,
        env,
        "-c",
        f"""
        SELECT public.complete_handoff_execution('{user}', '{handoff}', '{old_token}');
    """,
    )
    assert expired == "f", expired
    recovered = json.loads(
        _run(
            database,
            env,
            "-c",
            f"""
        SELECT public.claim_handoff_execution('{user}', '{handoff}', 'recovery');
    """,
        )
    )
    assert recovered["status"] == "claimed", recovered["status"]
    row = recovered["handoff"]
    assert row["execution_session_id"] == target
    assert row["execution_clock_at"] == first["execution_clock_at"]
    assert row["execution_plan"] == json.loads(plan)
    assert row["execution_attempts"] == 2
    new_token = row["execution_claim_token"]
    assert new_token != old_token
    checks = json.loads(
        _run(
            database,
            env,
            "-c",
            f"""
        SELECT json_build_object(
          'old_complete', public.complete_handoff_execution('{user}','{handoff}','{old_token}'),
          'old_plan', public.save_handoff_execution_plan(
            '{user}','{handoff}','{old_token}','{plan}'));
    """,
        )
    )
    assert checks == {"old_complete": False, "old_plan": False}, checks
    assert (
        _run(
            database,
            env,
            "-c",
            f"""
        SELECT public.complete_handoff_execution('{user}', '{handoff}', '{new_token}');
    """,
        )
        == "t"
    )
    terminal = json.loads(
        _run(
            database,
            env,
            "-c",
            f"""
        SELECT public.claim_handoff_execution('{user}', '{handoff}', 'late');
    """,
        )
    )
    assert terminal == {"status": "executed"}, terminal
    print(
        "PASS: expired token fenced; closed bound Session/clock/plan retained; "
        "terminal replay refused"
    )
    print("Scope: durable claim/replay state only; no model, Tool, Telegram, or Supabase calls")


if __name__ == "__main__":
    main()
