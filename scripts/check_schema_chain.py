"""Prove the schema-version gate is real, in both directions.

Two failures are invisible to the in-database assertions, because those only ever run
against a complete chain:

1. Migration 014 could blind-seed the ledger instead of verifying the chain. Then a
   database missing a migration still reports revision 14. This builds deliberately
   incomplete chains and requires 014 to refuse each one.
2. A migration could be applied without recording its ledger row. `max(version)` then
   reports a LOWER revision than the database actually is and the startup gate passes.
   That direction fails open, so the ledger head is compared with the code's constant.

Connection comes from the standard libpq environment (PGHOST, PGPORT, PGUSER,
PGPASSWORD); PGDATABASE names the already-built complete database.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.schema import EXPECTED_SCHEMA_VERSION  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS = REPO / "migrations"
BOOTSTRAP = REPO / "tests" / "sql" / "bootstrap_supabase_roles.sql"

# Chains that are constructible with one migration removed. The others cannot be built
# at all, because a later migration references an object the skipped one creates.
CONSTRUCTIBLE_SKIPS = ("003", "004", "007", "008", "009", "010", "012", "013")
# The migration whose refusal is under test. Only migrations before it take part in the
# incomplete chains, and only migrations before it can appear in CONSTRUCTIBLE_SKIPS — a
# later one is applied after the gate and so can never be missing when the gate runs.
GATE_MIGRATION = 14


def _psql(database: str, *args: str, owner: bool = False) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.pop("PGDATABASE", None)
    if owner:
        # Building a chain needs the owning role. Inheriting a caller's
        # `PGOPTIONS=-c role=...` would make every statement fail and the probe would
        # then report "unbuildable" instead of actually testing anything.
        env.pop("PGOPTIONS", None)
    return subprocess.run(
        ["psql", "-v", "ON_ERROR_STOP=1", "-q", "-t", "-A", "-d", database, *args],
        capture_output=True,
        text=True,
        env=env,
    )


class ProbeSetupError(RuntimeError):
    """A maintenance statement failed, so nothing after it can be trusted."""


def _maintenance(statement: str) -> None:
    # A silently failing DROP/CREATE leaves a stale database behind and every later
    # measurement then describes the wrong database. Never ignore this return code.
    result = _psql("postgres", "-c", statement, owner=True)
    if result.returncode != 0:
        raise ProbeSetupError(f"{statement}: {result.stderr.strip()}")


def _ledger_head_matches() -> bool:
    result = _psql(
        os.environ.get("PGDATABASE", "postgres"),
        "-c",
        "SELECT public.get_app_schema_version();",
    )
    if result.returncode != 0:
        print("FAIL: could not read the schema ledger")
        print(result.stderr.strip())
        return False

    reported = result.stdout.strip()
    if reported != str(EXPECTED_SCHEMA_VERSION):
        print(
            f"FAIL: the database reports schema revision {reported!r} but the code "
            f"expects {EXPECTED_SCHEMA_VERSION}. A migration applied without recording "
            "its ledger row reports a lower revision than the database actually is."
        )
        return False

    print(f"ok: database and code agree on schema revision {EXPECTED_SCHEMA_VERSION}")
    return True


def _refuses_incomplete_chain(skip: str, scratch: str) -> bool | None:
    """Return True if 014 refused, False if it certified, None if unbuildable."""
    _maintenance(f"DROP DATABASE IF EXISTS {scratch};")
    _maintenance(f"CREATE DATABASE {scratch};")

    # Everything below 014, minus the skipped one. Migrations *after* 014 must be excluded
    # too: they run after it in the real chain, so applying one to a database 014 has not
    # touched fails on objects 014 creates, and every probe would then report "unbuildable"
    # instead of testing anything.
    files = [BOOTSTRAP] + [
        path
        for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
        if not path.name.startswith(f"{skip}_") and int(path.name[:3]) < GATE_MIGRATION
    ]
    args: list[str] = []
    for path in files:
        args += ["-f", str(path)]

    if _psql(scratch, *args, owner=True).returncode != 0:
        return None

    migration = next(MIGRATIONS.glob(f"{GATE_MIGRATION:03d}_*.sql"))
    applied = _psql(scratch, "-f", str(migration), owner=True)
    _maintenance(f"DROP DATABASE IF EXISTS {scratch};")
    if applied.returncode == 0:
        return False
    # Refusing for an unrelated reason would score a green line without testing anything,
    # so the refusal must be the chain check speaking.
    if f"migration {int(skip)} is not applied" not in applied.stderr:
        print(f"FAIL: the chain without migration {skip} failed for another reason:")
        print(applied.stderr.strip())
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch-db", default="amigo_chain_probe")
    args = parser.parse_args()

    try:
        ok = _ledger_head_matches()
    except ProbeSetupError as error:
        print(f"FAIL: the schema chain probe could not run: {error}")
        return 1

    for skip in CONSTRUCTIBLE_SKIPS:
        try:
            refused = _refuses_incomplete_chain(skip, args.scratch_db)
        except ProbeSetupError as error:
            print(f"FAIL: the schema chain probe could not run: {error}")
            return 1
        if refused is None:
            print(f"FAIL: the chain without migration {skip} could not be built, so this")
            print("      probe no longer proves anything. Update CONSTRUCTIBLE_SKIPS.")
            ok = False
        elif refused:
            print(f"ok: migration 014 refused a chain missing migration {skip}")
        else:
            print(f"FAIL: migration 014 certified a chain missing migration {skip}")
            ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
