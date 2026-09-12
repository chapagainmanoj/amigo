# Review: Application Schema Version Migration 014

Status: awaiting project-owner approval
Reviewer: independent agent (implementation and review performed by different agents)
Prepared: 2026-09-12

## Purpose

Issue 16 requires the application to refuse to start against anything but its exact schema
revision. `src/schema.py` sets `EXPECTED_SCHEMA_VERSION = 14` and `src/startup.py` calls
`store.verify_schema_version(...)` before any scheduler-owned side effect, which invokes the
`get_app_schema_version` RPC through `src/memory/store.py`. That function exists in no migration,
so today every database built from this chain fails startup. This migration supplies it.

## Reconstruction note

The previously reviewed proposal bytes were lost when the OS cleaned `/tmp` between sessions.
This is a fresh reconstruction. Its hashes differ from the historical ones; it is not an exact
reproduction and is not claimed to be.

- proposal `014_application_schema_version.sql`:
  `f32924703d9b4a4c96dc492ee4077786d4898f9381da76011a170f3482242632`
- assertions `app_schema_version.sql`:
  `f58687e753be47f9a5cbb6073a60373d49208f3e315f0c700a84fffeb2922da9`
- chain guard `check_schema_chain.py`:
  `19698b3b0d818ce12198b32844e8101d634efa60659ac70ce473397135400e8c`
- historical proposal hash (not reproduced):
  `43e26e5363320e8441f5465167a6a9a89c7e29a6b0782bd3ca248cd17995bec9`
- historical assertions hash (not reproduced):
  `06be28fed547d14b83aaa07409b60e5d5ffdff710c29a5950369c324fd00e807`

## The design decision worth your attention

A schema ledger seeded with `1..14` would *assert* the chain reached revision 14. It would say so
just as confidently on a database missing migrations 012 and 013, which is exactly the failure
this gate exists to prevent.

So the version is **earned, not asserted**. Before recording anything, migration 014 checks for an
object that only each prior migration creates — `public.user_profiles` for 001, through
`public.get_activation_state` for 013 — and refuses the whole migration otherwise:

> **Correction after independent review.** The first draft of this migration used
> `public.issue_pairing_token` as the sentinel for migration 003. That was wrong: migration 013
> re-creates that function with `CREATE OR REPLACE`, so it is the one sentinel in the list created
> by two migrations. A chain built without 003 therefore passed and reported revision 14 — while
> missing `public.complete_pairing`, which the Pairing flow calls, and with row-level security
> disabled on `public.pairing_tokens`, which is the security fix 003 exists to deliver. That is
> worse than having no gate, because it converts an unverified assumption into a green check. The
> sentinel is now `public.complete_pairing`, which only 003 creates. Two further defects were fixed
> in the same pass: the policy check matched `policyname` globally, though policy names are unique
> only per table (now matched as `schema.table.policy`), and the `CASE` had no `ELSE`, so an
> unhandled check kind silently recorded the migration as applied (now `ELSE FALSE`).

```
ERROR:  migration 13 is not applied: missing function public.get_activation_state
```

Because the migration is one transaction, a refusal leaves `get_app_schema_version` non-existent.
The application then fails closed at startup on a missing RPC rather than booting against a
half-built schema. Verified: applying 014 to a chain stopping at 012 refuses, and
`SELECT count(*) FROM pg_proc WHERE proname='get_app_schema_version'` is `0` afterwards.

The reported revision is `max(version)`, not a row count, so a database carrying a *later*
migration reports that higher number and also fails the exact-version gate. Future migrations must
insert their own row; this is the one ongoing obligation the design creates.

## Verification performed before requesting approval

- The chain plus 013, 014, and both assertion files applies clean to a fresh PostgreSQL 15.12
  database.
- End-to-end against the real application gate: the database reports `14`,
  `require_schema_version` accepts it, and rejects the string `'14'`, `13`, `15`, `None`, and
  `True`.
- Mutation testing found two genuine gaps in an earlier version of these assertions. A
  `count(*)`-based implementation passed because a complete 1–14 ledger has count equal to max;
  a non-contiguous-version test now kills it. The second — deleting the earned-chain verification
  entirely — cannot be caught by assertions that only ever run on a complete chain, which is why
  the fail-closed CI step below is part of the adoption rather than an optional extra.
- Independent review found four further surviving mutants that the first report did not disclose:
  a blind-seeded ledger, a weak sentinel, an unhandled check kind, and a dropped
  `ENABLE ROW LEVEL SECURITY`. The first three are now killed by
  `scripts/check_schema_chain.py`, which builds each constructible incomplete chain and requires
  the migration to refuse it. The RLS mutant remains uncovered, because the privilege assertions
  read grants rather than RLS; it is defence in depth on a table no non-owner role can reach.
- The design's one ongoing obligation — every future migration must record its own ledger row — is
  **not** self-enforcing, and it fails **open**: a migration applied without its row makes
  `max(version)` report a lower revision than the database actually is, and the startup gate then
  passes. `scripts/check_schema_chain.py` compares the ledger head with
  `src.schema.EXPECTED_SCHEMA_VERSION`, and a held test ties that constant to the highest
  migration file on disk, so both halves of the obligation are checked rather than trusted.

## Adoption changes that must land in the same change

- `.github/workflows/ci.yml`: append `-f migrations/014_application_schema_version.sql` then
  `-f tests/sql/app_schema_version.sql` to the psql chain, and add a step running
  `python scripts/check_schema_chain.py`, which both compares the ledger head with the code's
  constant and requires migration 014 to refuse each of the eight constructible incomplete chains.
- `scripts/check_schema_chain.py` moves in alongside the migration.
- `tests/test_schema_version.py` gains the held test tying `EXPECTED_SCHEMA_VERSION` to the highest
  migration file on disk. It fails today on purpose, because the chain ends at 013 while the
  constant says 14; it turns green exactly when this migration lands.
- `README.md`: add step 16, a sentence in the numeric-order paragraph, and remove the preflight
  warning block entirely, since the worktree's schema chain becomes complete.
- The remaining `014` qualifications in `README.md`, `docs/what-is-amigo.md`,
  `docs/capability-matrix.md`, and `docs/pre-launch-gap-analysis.md` are retired.

## Proposed migration

```sql
BEGIN;

CREATE TABLE public.schema_migrations (
  version INT PRIMARY KEY CHECK (version > 0),
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.schema_migrations FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.schema_migrations TO service_role;

-- The recorded chain revision must be earned, not asserted. Each prior migration is
-- represented by an object only that migration creates; a chain missing any of them
-- fails here rather than reporting a version the database does not actually have.
DO $$
DECLARE
  expected CONSTANT TEXT[][] := ARRAY[
    ['1',  'table',    'public.user_profiles'],
    ['2',  'table',    'public.pairing_tokens'],
    ['3',  'function', 'public.complete_pairing'],
    ['4',  'policy',   'public.tasks.task_select_own'],
    ['5',  'function', 'public.create_task_command'],
    ['6',  'function', 'public.claim_scheduler_outbox'],
    ['7',  'function', 'public.resolve_task_command'],
    ['8',  'function', 'public.apply_later_command'],
    ['9',  'function', 'public.claim_telegram_update'],
    ['10', 'function', 'public.get_dashboard_snapshot'],
    ['11', 'function', 'public.get_reminder_reliability_health'],
    ['12', 'function', 'public.move_task_planning_day_command'],
    ['13', 'function', 'public.get_activation_state']
  ];
  entry TEXT[];
  present BOOLEAN;
BEGIN
  FOREACH entry SLICE 1 IN ARRAY expected
  LOOP
    present := CASE entry[2]
      WHEN 'table' THEN to_regclass(entry[3]) IS NOT NULL
      WHEN 'function' THEN EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS proc
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = proc.pronamespace
        WHERE namespace.nspname || '.' || proc.proname = entry[3]
      )
      WHEN 'policy' THEN EXISTS (
        SELECT 1 FROM pg_catalog.pg_policies
        WHERE schemaname || '.' || tablename || '.' || policyname = entry[3]
      )
      -- A verification loop must never default to "applied" for an unhandled kind.
      ELSE FALSE
    END;

    IF NOT present THEN
      RAISE EXCEPTION
        'migration % is not applied: missing % %', entry[1], entry[2], entry[3];
    END IF;

    INSERT INTO public.schema_migrations (version) VALUES (entry[1]::INT);
  END LOOP;

  INSERT INTO public.schema_migrations (version) VALUES (14);
END;
$$;

CREATE OR REPLACE FUNCTION public.get_app_schema_version()
RETURNS INT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT max(version) FROM public.schema_migrations;
$$;

REVOKE ALL ON FUNCTION public.get_app_schema_version() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_app_schema_version() TO service_role;

COMMIT;
```

## Proposed assertions (tests/sql/app_schema_version.sql)

```sql
\set ON_ERROR_STOP on

SET ROLE service_role;

DO $$
DECLARE
  reported INT;
BEGIN
  reported := public.get_app_schema_version();

  IF reported <> 14 THEN
    RAISE EXCEPTION 'Applied migration chain reported schema version %, expected 14', reported;
  END IF;

  -- The application's require_schema_version refuses anything that is not an exact
  -- integer, so the RPC must not return a string, numeric, or NULL.
  IF pg_typeof(public.get_app_schema_version()) <> 'integer'::regtype THEN
    RAISE EXCEPTION 'Schema version is not an exact integer';
  END IF;

  IF (SELECT count(*) FROM public.schema_migrations) <> 14
    OR (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 14) <> 14
  THEN
    RAISE EXCEPTION 'Schema ledger does not record every migration in the chain exactly once';
  END IF;

  IF EXISTS (
    SELECT 1 FROM generate_series(1, 14) AS expected(version)
    WHERE NOT EXISTS (
      SELECT 1 FROM public.schema_migrations AS applied
      WHERE applied.version = expected.version
    )
  ) THEN
    RAISE EXCEPTION 'Schema ledger has a gap in the applied migration chain';
  END IF;

  -- A later migration must move the reported revision, so a database ahead of the
  -- application also fails the exact-version startup gate.
  INSERT INTO public.schema_migrations (version) VALUES (15);
  IF public.get_app_schema_version() <> 15 THEN
    RAISE EXCEPTION 'Schema version did not follow the applied chain forward';
  END IF;
  DELETE FROM public.schema_migrations WHERE version = 15;

  -- The revision is the highest applied migration, not a count of rows: a database
  -- carrying a non-contiguous later migration must report that migration's number.
  INSERT INTO public.schema_migrations (version) VALUES (20);
  IF public.get_app_schema_version() <> 20 THEN
    RAISE EXCEPTION 'Schema version is derived from a row count rather than the chain head';
  END IF;
  DELETE FROM public.schema_migrations WHERE version = 20;

  IF public.get_app_schema_version() <> 14 THEN
    RAISE EXCEPTION 'Schema version did not return to the real chain revision';
  END IF;
END;
$$;

DO $$
DECLARE
  definer BOOLEAN;
  config TEXT[];
BEGIN
  SELECT proc.prosecdef, proc.proconfig
  INTO definer, config
  FROM pg_catalog.pg_proc AS proc
  JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = proc.pronamespace
  WHERE namespace.nspname = 'public'
    AND proc.proname = 'get_app_schema_version';

  IF NOT FOUND OR NOT definer THEN
    RAISE EXCEPTION 'Schema version function is not SECURITY DEFINER';
  END IF;
  IF config IS NULL OR NOT ('search_path=pg_catalog, public' = ANY(config)) THEN
    RAISE EXCEPTION 'Schema version function did not pin its search_path';
  END IF;
END;
$$;

RESET ROLE;
SET ROLE anon;

DO $$
BEGIN
  IF has_function_privilege(current_user, 'public.get_app_schema_version()', 'EXECUTE')
    OR has_table_privilege(current_user, 'public.schema_migrations', 'SELECT')
  THEN
    RAISE EXCEPTION 'Anonymous role retained schema-version access';
  END IF;
END;
$$;

RESET ROLE;
SET ROLE authenticated;

DO $$
BEGIN
  IF has_function_privilege(current_user, 'public.get_app_schema_version()', 'EXECUTE')
    OR has_table_privilege(current_user, 'public.schema_migrations', 'SELECT')
  THEN
    RAISE EXCEPTION 'Authenticated role retained schema-version access';
  END IF;
END;
$$;

RESET ROLE;
```

## Proposed chain guard (scripts/check_schema_chain.py)

```python
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


def _maintenance(statement: str) -> None:
    _psql("postgres", "-c", statement, owner=True)


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

    files = [BOOTSTRAP] + [
        path
        for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql"))
        if not path.name.startswith(f"{skip}_") and not path.name.startswith("014_")
    ]
    args: list[str] = []
    for path in files:
        args += ["-f", str(path)]

    if _psql(scratch, *args, owner=True).returncode != 0:
        return None

    migration = next(MIGRATIONS.glob("014_*.sql"))
    certified = _psql(scratch, "-f", str(migration), owner=True).returncode == 0
    _maintenance(f"DROP DATABASE IF EXISTS {scratch};")
    return not certified


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch-db", default="amigo_chain_probe")
    args = parser.parse_args()

    ok = _ledger_head_matches()

    for skip in CONSTRUCTIBLE_SKIPS:
        refused = _refuses_incomplete_chain(skip, args.scratch_db)
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
```

## Review checklist

- [x] The RPC name, return type, and exact-integer contract match `src/memory/store.py` and
      `src/schema.py`.
- [x] The recorded revision is verified against real schema objects, not asserted, and each
      sentinel is created by exactly one migration.
- [x] Every constructible incomplete chain refuses the migration and leaves no
      `get_app_schema_version` behind; verified for migrations 003, 004, 007, 008, 009, 010, 012,
      and 013, the eight skips that can actually be built.
- [x] An unhandled check kind refuses rather than defaulting to applied.
- [x] The ledger head is compared with the code's constant, covering the fail-open direction the
      startup gate cannot see.
- [x] The revision follows the chain head, not a row count.
- [x] The real `require_schema_version` accepts the real reported value and rejects drift,
      coercion, and `None`.
- [x] `SECURITY DEFINER` and a pinned `search_path`, matching the chain's convention.
- [x] Anonymous and authenticated roles lose both the ledger table and the function.

## Decision

Not yet approved. Requested authorization: `approve migration 014`.
