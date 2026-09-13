"""Fail if create_activation_test_command can deadlock against get_activation_state.

Scope, stated plainly, because a probe that overstates its coverage is worse than none:

- Only the forced interleave is load-bearing. The randomised trials below run against a fully
  paired profile, so every session derives the same advisory key and `pg_advisory_xact_lock`
  serialises them — the row-lock order is unobservable there by construction. They are kept as
  a cheap liveness check on the functions, not as evidence about ordering.
- The forced interleave drives exactly one shape: `create_activation_test_command` against
  `get_activation_state` with `supabase_auth_id` moving from NULL. An inversion that only
  appears while holding an `activation_journeys` lock, or between two other functions, is
  invisible to it.
- It does NOT cover `complete_pairing`, which takes two `user_profiles` row locks by different
  keys with no advisory lock and can deadlock against itself — see issue 16.

`tests/test_migration_lock_order.py` is the guard that covers the chain as a whole: it reads
the migration text, so it needs no database, no timing, and no luck. This probe exists for the
narrower job of catching an ordering that looks right on paper but deadlocks in execution.


Migration 013's functions take an auth-id advisory lock and row locks on
`user_profiles` and `activation_journeys`. If any of them takes those row locks in a
different order, a participant submitting the test Reminder deadlocks against the
dashboard polling `GET /api/activation`, and neither call site retries.

Two interleaves are driven, because the first one alone proves very little. In the
paired trial every session derives the same advisory key, so `pg_advisory_xact_lock`
serialises them and the row-lock order is unobservable by construction. The racing
trial is the one that matters: `complete_pairing` sets `supabase_auth_id` while the
test command is already past its unlocked read, so the two sides disagree about the
advisory key and only the row-lock order stands between them and a deadlock.

Connection comes from the standard libpq environment (PGHOST, PGPORT, PGUSER,
PGDATABASE, PGPASSWORD), so it needs no arguments in CI.

Usage: python scripts/check_activation_lock_order.py [--trials N]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

CONCURRENT_READERS = 4
FORCED_INTERLEAVE_ATTEMPTS = 5


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


def _forced_interleave() -> tuple[bool, list[str]]:
    """Drive the one interleave that a probabilistic probe will almost never hit.

    Racing the calls and hoping is not evidence: the window between the test command's
    unlocked profile read and its row locks is microseconds wide, and thousands of random
    trials can miss it. Two helper sessions hold the advisory key and the `user_profiles`
    row so the interleave happens every time, and `complete_pairing` commits inside that
    window. If the row-lock order is inconsistent, this deadlocks deterministically.
    """
    auth, user = str(uuid.uuid4()), str(uuid.uuid4())
    chat = uuid.uuid4().int % 10**12
    token = uuid.uuid4().hex
    _require(f"SELECT public.acknowledge_activation_terms('{auth}','2026-08-29');")
    _require(
        "INSERT INTO public.user_profiles(user_id, telegram_chat_id, supabase_auth_id)"
        f" VALUES ('{user}',{chat},NULL);",
    )
    _require(
        f"SELECT public.issue_pairing_token('{token}','{auth}',"
        "now() + interval '10 minutes');"
    )

    results: dict[str, subprocess.CompletedProcess] = {}

    def at(delay: float, name: str, statement: str) -> threading.Thread:
        def run() -> None:
            time.sleep(delay)
            results[name] = _psql(statement)

        thread = threading.Thread(target=run)
        thread.start()
        return thread

    threads = [
        # Holds the advisory key the test command computes while supabase_auth_id is NULL.
        at(
            0.0,
            "hold_advisory",
            f"BEGIN; SELECT pg_advisory_xact_lock(hashtextextended('{user}',0));"
            " SELECT pg_sleep(6); COMMIT;",
        ),
        # Reads the profile unlocked, then parks on the advisory lock above.
        at(1.0, "create", _create_statement(user)),
        # Pairing commits inside that window, so the advisory key is now stale.
        at(2.0, "pair", f"SELECT public.complete_pairing('{token}',{chat});"),
        # Holds the user_profiles row so the test command parks there next.
        at(
            3.5,
            "hold_profile",
            f"BEGIN; SELECT user_id FROM public.user_profiles WHERE user_id='{user}'"
            " FOR UPDATE; SELECT pg_sleep(8); COMMIT;",
        ),
        # The dashboard read: locks activation_journeys first, then queues on user_profiles.
        at(7.5, "read", f"SELECT public.get_activation_state('{auth}');"),
    ]
    for thread in threads:
        thread.join()

    for name in ("hold_advisory", "pair", "hold_profile"):
        if results[name].returncode != 0:
            raise SetupError(f"{name}: {results[name].stderr.strip().splitlines()[0]}")
    # complete_pairing reports its outcome in the payload, not the exit code, so a silent
    # `conflict` or `invalid_token` would leave the identity unchanged and the interleave
    # would test nothing.
    if '"status": "paired"' not in results["pair"].stdout:
        raise SetupError(f"pair did not pair: {results['pair'].stdout.strip()[:120]}")
    # The command must have travelled the whole lock sequence and answered from the identity
    # re-check under the row lock. Any other outcome — success, a missing function, a mutant
    # that raises before taking a lock — means this trial tested nothing.
    stderr = results["create"].stderr
    deadlocks = [
        f"{name}: {result.stderr.splitlines()[0]}"
        for name, result in results.items()
        if "deadlock" in result.stderr
    ]
    # On a loaded machine the sleep-based choreography does not always line up. That is a
    # trial that proved nothing, not a pass, and it is reported separately from a genuine
    # setup failure so it can be retried rather than mistaken for a result.
    formed = "activation_pairing_changed" in stderr or bool(deadlocks)
    return formed, deadlocks


def _create_statement(user: str) -> str:
    scheduled = datetime.now(UTC) + timedelta(minutes=2)
    local = scheduled.astimezone(ZoneInfo("America/Toronto"))
    return (
        f"SELECT public.create_activation_test_command('{user}','k-{uuid.uuid4().hex}',"
        f"'{'a' * 64}','probe',false,'{scheduled.isoformat()}','{local.date()}',"
        f"'{local.time().replace(microsecond=0)}','America/Toronto');"
    )


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

    create = _create_statement(user)

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

    # Every named call must have run. `any()` here was satisfied by the readers alone, so a
    # command side that never executed — because the function was missing, or raised before
    # taking a single lock — still scored a pass.
    for name, result in results.items():
        if result.returncode != 0 and "deadlock" not in result.stderr:
            raise SetupError(
                f"{name}: " + (
                    result.stderr.strip().splitlines()[0] if result.stderr else "did not execute"
                )
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
        for _attempt in range(1, FORCED_INTERLEAVE_ATTEMPTS + 1):
            formed, found = _forced_interleave()
            deadlocks.extend(found)
            if formed:
                break
        else:
            print(
                "FAIL: the forced interleave never formed in "
                f"{FORCED_INTERLEAVE_ATTEMPTS} attempts, so the lock order was never "
                "exercised. This is not a pass."
            )
            return 1
    except SetupError as error:
        print(f"FAIL: the deadlock probe could not run: {error}")
        print("This check proves nothing unless the Activation functions are reachable.")
        return 1

    calls = args.trials * (CONCURRENT_READERS + 1) + 5
    if deadlocks:
        print(f"FAIL: {len(deadlocks)} deadlocks in {args.trials} trials ({calls} calls)")
        for line in deadlocks[:5]:
            print(f"  {line}")
        print("Every Activation function must take its row locks in the same order —")
        print("activation_journeys before user_profiles. See migration 013.")
        return 1

    print(
        f"ok: the forced interleave held, and {args.trials} trials ({calls} calls) "
        "found no deadlock. Only the forced interleave tests lock order; see this "
        "script's docstring for what it does not cover."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
