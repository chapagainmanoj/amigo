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
