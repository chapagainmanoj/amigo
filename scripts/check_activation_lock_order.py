"""Fail if the Activation functions can deadlock against each other.

Migration 013's functions take an auth-id advisory lock and a `user_profiles` row
lock. If any of them takes the row lock first, a participant submitting the test
Reminder deadlocks against the dashboard polling `GET /api/activation`, and neither
call site retries. This drives that exact interleave.

Connection comes from the standard libpq environment (PGHOST, PGPORT, PGUSER,
PGDATABASE, PGPASSWORD), so it needs no arguments in CI.

Usage: python scripts/check_activation_lock_order.py [--trials N]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

CONCURRENT_READERS = 4


class SetupError(RuntimeError):
    """A probe precondition did not hold, so the trial proves nothing."""


def _psql(statement: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["psql", "-v", "ON_ERROR_STOP=1", "-t", "-A", "-c", statement],
        capture_output=True,
        text=True,
    )


def _require(statement: str) -> subprocess.CompletedProcess:
    """Run a setup statement that must succeed.

    Without this the probe passes vacuously: if every setup statement errors, no
    Activation function is ever invoked, nothing deadlocks, and the check reports
    success against a database that does not even have the functions.
    """
    result = _psql(statement)
    if result.returncode != 0:
        raise SetupError(result.stderr.strip().splitlines()[0] if result.stderr else statement)
    return result


def _trial() -> list[str]:
    auth, user = str(uuid.uuid4()), str(uuid.uuid4())
    chat = uuid.uuid4().int % 10**12
    _require(f"SELECT public.acknowledge_activation_terms('{auth}','2026-08-29');")
    _require(
        "INSERT INTO public.user_profiles(user_id, telegram_chat_id, supabase_auth_id)"
        f" VALUES ('{user}',{chat},'{auth}');",
    )
    _require(
        f"SELECT public.update_activation_profile('{auth}','Probe','America/Toronto',"
        "'07:00','22:30');",
    )

    scheduled = datetime.now(UTC) + timedelta(minutes=2)
    local = scheduled.astimezone(ZoneInfo("America/Toronto"))
    create = (
        f"SELECT public.create_activation_test_command('{user}','k-{uuid.uuid4().hex}',"
        f"'{'a' * 64}','probe',false,'{scheduled.isoformat()}','{local.date()}',"
        f"'{local.time().replace(microsecond=0)}','America/Toronto');"
    )

    results: dict[str, subprocess.CompletedProcess] = {}

    def run(name: str, statement: str) -> None:
        results[name] = _psql(statement)

    threads = [threading.Thread(target=run, args=("create", create))]
    threads += [
        threading.Thread(
            target=run, args=(f"read{index}", f"SELECT public.get_activation_state('{auth}');")
        )
        for index in range(CONCURRENT_READERS)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if not any(
        result.returncode == 0 or "deadlock" in result.stderr
        for result in results.values()
    ):
        broken = next(iter(results.values()))
        raise SetupError(
            broken.stderr.strip().splitlines()[0] if broken.stderr else "no call executed"
        )

    return [
        f"{name}: {result.stderr.splitlines()[0]}"
        for name, result in results.items()
        if "deadlock" in result.stderr
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    args = parser.parse_args()

    deadlocks: list[str] = []
    try:
        for _ in range(args.trials):
            deadlocks.extend(_trial())
    except SetupError as error:
        print(f"FAIL: the deadlock probe could not run: {error}")
        print("This check proves nothing unless the Activation functions are reachable.")
        return 1

    calls = args.trials * (CONCURRENT_READERS + 1)
    if deadlocks:
        print(f"FAIL: {len(deadlocks)} deadlocks in {args.trials} trials ({calls} calls)")
        for line in deadlocks[:5]:
            print(f"  {line}")
        print("The Activation functions must take the auth-id advisory lock before the")
        print("user_profiles row lock. See migration 013.")
        return 1

    print(f"ok: no deadlocks in {args.trials} trials ({calls} concurrent calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
