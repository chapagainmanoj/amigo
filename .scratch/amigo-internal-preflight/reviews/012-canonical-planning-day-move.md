# Review: Canonical Planning Day Move Migration 012

Status: approved
Reviewer: independent agent (implementation and review performed by different agents)
Prepared: 2026-09-11

## Purpose

Issue 14 requires the Gate A planning-day case to run against the release candidate. The agent
Tool `move_task_planning_day` (`src/agent/agent.py`) and `MoveTaskPlanningDayCommand`
(`src/commands/tasks.py`) already call `MemoryStore.move_task_planning_day_command`, which invokes
the `move_task_planning_day_command` RPC. That function exists in no migration 001-011, so the
Supabase-backed path cannot run. This service-only function moves one owned pending Task to an
explicit Planning Day in one idempotent transaction, mirroring `InMemoryStore` and `FakeStore`.

## Reconstruction note

The previously reviewed proposal bytes were lost when the OS cleaned `/tmp` between sessions. This
is a fresh reconstruction from the current application code, fakes, and tests. Its hashes
therefore differ from the historical ones, which is expected and is not an exact reproduction.

- proposal `012_canonical_planning_day_move.sql`:
  `f8a77b5db981b1f6e953bf40fc69c97cb2dc5007be9502e538b5a545ab7dc326`
- assertions `move_task_planning_day_command.sql`:
  `fafdd3cdf27b64d01dd5bd0ebb56fe2f0a63a2c493437a3947362c133860ba8f`
- historical proposal hash (not reproduced):
  `a338bbbfb03c04b8e6e9cc28ab6dc2ff49fa1ae1b7f9ae6b4bf419bd8ff86a86`
- historical assertions hash (not reproduced):
  `46f381b201a6f1f1c22bff4d3fcb0074025638c588f9c52978481f89a250390d`

## Verification performed before requesting approval

- The unchanged CI chain was replayed on a clean PostgreSQL 15.12 cluster as a baseline: pass.
- The chain plus this proposal plus its assertions: pass.
- Mutation testing by the implementing agent: ownership filter, version bump, receipt write, and
  pending-status check removals are each caught by the assertions.
- Independent adversarial mutation testing by the reviewing agent: 15 mutants, 11 killed. The
  assertions were then extended to also pin `command_type`, `prosecdef`, and `search_path`, which
  kills three of the survivors. The three remaining survivors are the advisory-lock and
  `FOR UPDATE` removals, which need a two-session concurrency harness; no existing file under
  `tests/sql/` tests concurrency, `proconfig`, or `prosecdef`, so this is a chain-wide convention
  gap rather than a defect specific to 012.
- The reviewer confirmed under a real two-session harness that concurrent identical commands
  replay rather than double-apply, that a concurrent `resolve_task_command` serializes without
  deadlock, and that `anon`/`authenticated` genuinely lose EXECUTE and UPDATE.

## Adoption changes that must land in the same change

Approval of the SQL alone would leave the assertion file unexecuted. These land together:

- `.github/workflows/ci.yml`: append to the end of the existing psql chain, after
  `tests/sql/reminder_reliability.sql`, in this order:
  `-f migrations/012_canonical_planning_day_move.sql` then
  `-f tests/sql/move_task_planning_day_command.sql`. Placement is constrained: the assertions
  depend on the participants seeded by `tests/sql/tenant_isolation.sql`.
- `README.md`: add step `14. Run migrations/012_canonical_planning_day_move.sql` and one sentence
  describing it in the numeric-order paragraph.

## Proposed migration

```sql
BEGIN;

CREATE OR REPLACE FUNCTION public.move_task_planning_day_command(
  p_user_id UUID,
  p_idempotency_key TEXT,
  p_payload_hash TEXT,
  p_task_id UUID,
  p_due_date DATE,
  p_expected_version BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  existing_receipt public.command_receipts%ROWTYPE;
  task_row public.tasks%ROWTYPE;
  command_result JSONB;
BEGIN
  IF p_user_id IS NULL OR NOT EXISTS (
    SELECT 1
    FROM public.user_profiles AS profile
    WHERE profile.user_id = p_user_id
  ) THEN
    RAISE EXCEPTION 'user_not_found';
  END IF;

  IF p_idempotency_key IS NULL
    OR length(btrim(p_idempotency_key)) NOT BETWEEN 1 AND 200
  THEN
    RAISE EXCEPTION 'invalid_idempotency_key';
  END IF;

  IF p_payload_hash IS NULL OR p_payload_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid_payload_hash';
  END IF;

  IF p_due_date IS NULL THEN
    RAISE EXCEPTION 'invalid_planning_day';
  END IF;

  IF p_expected_version IS NOT NULL AND p_expected_version < 1 THEN
    RAISE EXCEPTION 'invalid_task_version';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended(p_user_id::text || ':' || p_idempotency_key, 0)
  );

  SELECT receipt.*
  INTO existing_receipt
  FROM public.command_receipts AS receipt
  WHERE receipt.user_id = p_user_id
    AND receipt.idempotency_key = p_idempotency_key;

  IF FOUND THEN
    IF existing_receipt.payload_hash <> p_payload_hash THEN
      RAISE EXCEPTION 'idempotency_key_conflict';
    END IF;
    RETURN existing_receipt.result;
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_task_id::text, 0));

  SELECT task.*
  INTO task_row
  FROM public.tasks AS task
  WHERE task.task_id = p_task_id
    AND task.user_id = p_user_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'task_not_found';
  END IF;

  IF task_row.status <> 'pending' THEN
    RAISE EXCEPTION 'task_not_pending';
  END IF;

  IF p_expected_version IS NOT NULL
    AND task_row.version <> p_expected_version
  THEN
    RAISE EXCEPTION 'stale_task_version';
  END IF;

  UPDATE public.tasks
  SET
    due_date = p_due_date,
    version = version + 1
  WHERE task_id = p_task_id
  RETURNING * INTO task_row;

  command_result := jsonb_build_object('task', to_jsonb(task_row));

  INSERT INTO public.command_receipts (
    user_id,
    idempotency_key,
    command_type,
    payload_hash,
    result
  )
  VALUES (
    p_user_id,
    p_idempotency_key,
    'move_task_planning_day',
    p_payload_hash,
    command_result
  );

  RETURN command_result;
END;
$$;

REVOKE ALL ON FUNCTION public.move_task_planning_day_command(
  UUID, TEXT, TEXT, UUID, DATE, BIGINT
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.move_task_planning_day_command(
  UUID, TEXT, TEXT, UUID, DATE, BIGINT
) TO service_role;

COMMIT;
```

## Proposed assertions (tests/sql/move_task_planning_day_command.sql)

```sql
\set ON_ERROR_STOP on

INSERT INTO public.tasks(task_id, user_id, title, status, due_date)
VALUES
  (
    'aaaaaaaa-4300-0000-0000-000000000001',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'Move to an explicit planning day',
    'pending',
    NULL
  ),
  (
    'aaaaaaaa-4300-0000-0000-000000000002',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'Already resolved Task',
    'completed',
    NULL
  );

SET ROLE service_role;

DO $$
DECLARE
  first_result JSONB;
  replay_result JSONB;
  second_move JSONB;
  receipt_count INT;
BEGIN
  first_result := public.move_task_planning_day_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-move-planning-day',
    repeat('a', 64),
    'aaaaaaaa-4300-0000-0000-000000000001',
    DATE '2026-09-02',
    1
  );
  replay_result := public.move_task_planning_day_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-move-planning-day',
    repeat('a', 64),
    'aaaaaaaa-4300-0000-0000-000000000001',
    DATE '2026-09-02',
    1
  );

  IF replay_result <> first_result
    OR first_result #>> '{task,due_date}' <> '2026-09-02'
    OR first_result #>> '{task,version}' <> '2'
    OR first_result #>> '{task,status}' <> 'pending'
    OR first_result ? 'task_version'
  THEN
    RAISE EXCEPTION 'Planning-day move did not return its canonical idempotent result';
  END IF;

  SELECT count(*)
  INTO receipt_count
  FROM public.command_receipts
  WHERE user_id = 'aaaaaaaa-0000-0000-0000-000000000001'
    AND idempotency_key = 'sql-move-planning-day'
    AND command_type = 'move_task_planning_day';

  IF receipt_count <> 1
    OR (
      SELECT version
      FROM public.tasks
      WHERE task_id = 'aaaaaaaa-4300-0000-0000-000000000001'
    ) <> 2
  THEN
    RAISE EXCEPTION 'Replayed planning-day move mutated state or duplicated its receipt';
  END IF;

  BEGIN
    PERFORM public.move_task_planning_day_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-move-planning-day',
      repeat('b', 64),
      'aaaaaaaa-4300-0000-0000-000000000001',
      DATE '2026-09-03',
      2
    );
    RAISE EXCEPTION 'Conflicting idempotency payload unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'idempotency_key_conflict' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.move_task_planning_day_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-move-stale',
      repeat('c', 64),
      'aaaaaaaa-4300-0000-0000-000000000001',
      DATE '2026-09-03',
      1
    );
    RAISE EXCEPTION 'Stale Task version unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'stale_task_version' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.move_task_planning_day_command(
      'bbbbbbbb-0000-0000-0000-000000000002',
      'sql-move-cross-tenant',
      repeat('d', 64),
      'aaaaaaaa-4300-0000-0000-000000000001',
      DATE '2026-09-03',
      2
    );
    RAISE EXCEPTION 'Cross-tenant planning-day move unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'task_not_found' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.move_task_planning_day_command(
      '00000000-0000-0000-0000-000000000000',
      'sql-move-unknown-actor',
      repeat('e', 64),
      'aaaaaaaa-4300-0000-0000-000000000001',
      DATE '2026-09-03',
      2
    );
    RAISE EXCEPTION 'Unknown actor planning-day move unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'user_not_found' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.move_task_planning_day_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-move-resolved-task',
      repeat('f', 64),
      'aaaaaaaa-4300-0000-0000-000000000002',
      DATE '2026-09-03',
      1
    );
    RAISE EXCEPTION 'Resolved Task planning-day move unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'task_not_pending' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.move_task_planning_day_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-move-null-day',
      repeat('a', 64),
      'aaaaaaaa-4300-0000-0000-000000000001',
      NULL,
      2
    );
    RAISE EXCEPTION 'Null planning day unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'invalid_planning_day' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.move_task_planning_day_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      '   ',
      repeat('a', 64),
      'aaaaaaaa-4300-0000-0000-000000000001',
      DATE '2026-09-03',
      2
    );
    RAISE EXCEPTION 'Blank idempotency key unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'invalid_idempotency_key' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.move_task_planning_day_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-move-bad-hash',
      'not-a-sha256-digest',
      'aaaaaaaa-4300-0000-0000-000000000001',
      DATE '2026-09-03',
      2
    );
    RAISE EXCEPTION 'Malformed payload hash unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'invalid_payload_hash' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.move_task_planning_day_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-move-bad-version',
      repeat('a', 64),
      'aaaaaaaa-4300-0000-0000-000000000001',
      DATE '2026-09-03',
      0
    );
    RAISE EXCEPTION 'Non-positive expected version unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'invalid_task_version' THEN
        RAISE;
      END IF;
  END;

  second_move := public.move_task_planning_day_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-move-unversioned',
    repeat('1', 64),
    'aaaaaaaa-4300-0000-0000-000000000001',
    DATE '2026-09-04',
    NULL
  );

  IF second_move #>> '{task,due_date}' <> '2026-09-04'
    OR second_move #>> '{task,version}' <> '3'
  THEN
    RAISE EXCEPTION 'Unversioned planning-day move did not advance the Task';
  END IF;

  IF (
    SELECT count(*)
    FROM public.tasks
    WHERE task_id = 'aaaaaaaa-4300-0000-0000-000000000002'
      AND due_date IS NULL
      AND status = 'completed'
      AND version = 1
  ) <> 1
  THEN
    RAISE EXCEPTION 'A rejected planning-day move changed the resolved Task';
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
  JOIN pg_catalog.pg_namespace AS namespace
    ON namespace.oid = proc.pronamespace
  WHERE namespace.nspname = 'public'
    AND proc.proname = 'move_task_planning_day_command';

  IF NOT FOUND OR NOT definer THEN
    RAISE EXCEPTION 'Planning-day move is not a SECURITY DEFINER function';
  END IF;
  IF config IS NULL
    OR NOT ('search_path=pg_catalog, public' = ANY(config))
  THEN
    RAISE EXCEPTION 'Planning-day move did not pin its search_path';
  END IF;
END;
$$;

RESET ROLE;
SET ROLE authenticated;

DO $$
BEGIN
  IF has_table_privilege(current_user, 'public.tasks', 'UPDATE')
    OR has_function_privilege(
      current_user,
      'public.move_task_planning_day_command(uuid,text,text,uuid,date,bigint)',
      'EXECUTE'
    )
  THEN
    RAISE EXCEPTION 'Authenticated role retained planning-day move privileges';
  END IF;
  IF NOT has_table_privilege(current_user, 'public.tasks', 'SELECT') THEN
    RAISE EXCEPTION 'Authenticated role lost Task read access';
  END IF;
END;
$$;

RESET ROLE;
```

## Review checklist

- [x] Matching replay returns the stored receipt result without re-applying the move.
- [x] A reused idempotency key with different input fails closed as `idempotency_key_conflict`.
- [x] Only an owned, pending Task can be moved; wrong-owner IDs report `task_not_found`.
- [x] A resolved Task reports `task_not_pending`, which maps to the fakes' "Task not found".
- [x] Stale `expected_version` fails closed; `NULL` expected version is accepted as unversioned.
- [x] The Task version advances exactly once per applied move, and never on a replay.
- [x] The returned envelope is exactly `{'task': <row>}`, matching all three store implementations
      and the only consumer, and deliberately omits the `task_version` key that 007 and 008 emit.
- [x] Every raised error string that is reachable through `MoveTaskPlanningDayCommand` is mapped by
      `_raise_command_error` to the same exception the fakes raise.
- [x] Anonymous and authenticated roles cannot execute the function or UPDATE `public.tasks`.
- [x] `SECURITY DEFINER`, pinned `search_path`, and the `proacl` are identical to migrations
      005, 007, and 008.
- [x] Past-date rejection is deliberately NOT enforced in the database. It lives at
      `src/agent/agent.py` because it is relative to the participant's timezone, and neither
      `InMemoryStore` nor `FakeStore` enforces it; a database check would break store mirroring.

## Decision

Approved by the project owner on 2026-09-11 in response to the request
`approve migration 012`. Added in the same change as:

- `migrations/012_canonical_planning_day_move.sql`
  (`f8a77b5db981b1f6e953bf40fc69c97cb2dc5007be9502e538b5a545ab7dc326`)
- `tests/sql/move_task_planning_day_command.sql`
  (`fafdd3cdf27b64d01dd5bd0ebb56fe2f0a63a2c493437a3947362c133860ba8f`)
- the `.github/workflows/ci.yml` chain extension, in numeric order at the tail
- `README.md` step 14, its numeric-order description, and the corrected preflight warning block
- the `013–014` corrections to `README.md`, `docs/what-is-amigo.md`, `docs/capability-matrix.md`,
  and `docs/pre-launch-gap-analysis.md`, which previously said `012–014`

Post-adoption verification: the chain parsed verbatim out of `.github/workflows/ci.yml` (27 files)
applied clean to a fresh PostgreSQL 15.12 database; 257 backend tests, Ruff, the Gate A contract
check, the scheduler smoke check, `git diff --check`, and the dashboard lint/build all pass.
