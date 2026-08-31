\set ON_ERROR_STOP on

INSERT INTO public.tasks(task_id, user_id, title, status)
VALUES
  (
    'aaaaaaaa-4100-0000-0000-000000000001',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'Resolve completed',
    'pending'
  ),
  (
    'aaaaaaaa-4100-0000-0000-000000000002',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'Resolve skipped',
    'pending'
  ),
  (
    'aaaaaaaa-4100-0000-0000-000000000003',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'Resolve cancelled',
    'pending'
  );

INSERT INTO public.reminders(
  reminder_id,
  task_id,
  user_id,
  scheduled_time,
  status,
  intended_local_date,
  intended_local_time,
  intended_timezone
)
VALUES (
  'aaaaaaaa-5100-0000-0000-000000000001',
  'aaaaaaaa-4100-0000-0000-000000000001',
  'aaaaaaaa-0000-0000-0000-000000000001',
  now() + INTERVAL '1 hour',
  'sent',
  current_date,
  TIME '12:00:00',
  'UTC'
);

SET ROLE service_role;

DO $$
DECLARE
  first_result JSONB;
  replay_result JSONB;
  repeated_result JSONB;
  skipped_result JSONB;
  cancelled_result JSONB;
BEGIN
  first_result := public.resolve_task_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-resolve-completed',
    repeat('a', 64),
    'aaaaaaaa-4100-0000-0000-000000000001',
    'completed',
    1,
    'aaaaaaaa-5100-0000-0000-000000000001'
  );
  replay_result := public.resolve_task_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-resolve-completed',
    repeat('a', 64),
    'aaaaaaaa-4100-0000-0000-000000000001',
    'completed',
    1,
    'aaaaaaaa-5100-0000-0000-000000000001'
  );

  IF replay_result <> first_result
    OR first_result #>> '{task,status}' <> 'completed'
    OR first_result ->> 'task_version' <> '2'
    OR first_result ->> 'transitioned' <> 'true'
    OR first_result ->> 'effect_state' <> 'queued'
    OR jsonb_array_length(first_result -> 'effects') <> 1
    OR first_result #>> '{reminders,0,status}' <> 'acknowledged'
  THEN
    RAISE EXCEPTION 'Resolve Task did not return its atomic canonical result';
  END IF;

  repeated_result := public.resolve_task_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-resolve-repeated',
    repeat('b', 64),
    'aaaaaaaa-4100-0000-0000-000000000001',
    'completed',
    NULL,
    'aaaaaaaa-5100-0000-0000-000000000001'
  );

  IF repeated_result ->> 'transitioned' <> 'false'
    OR repeated_result ->> 'effect_state' <> 'none'
    OR (
      SELECT count(*)
      FROM public.scheduler_outbox
      WHERE task_id = 'aaaaaaaa-4100-0000-0000-000000000001'
    ) <> 1
  THEN
    RAISE EXCEPTION 'Repeated Task resolution mutated state or duplicated effects';
  END IF;

  BEGIN
    PERFORM public.resolve_task_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-resolve-completed',
      repeat('f', 64),
      'aaaaaaaa-4100-0000-0000-000000000001',
      'completed',
      1,
      NULL
    );
    RAISE EXCEPTION 'Conflicting idempotency payload unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'idempotency_key_conflict' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.resolve_task_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-resolve-stale',
      repeat('c', 64),
      'aaaaaaaa-4100-0000-0000-000000000001',
      'completed',
      1,
      NULL
    );
    RAISE EXCEPTION 'Stale Task version unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'stale_task_version' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.resolve_task_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-resolve-conflicting-outcome',
      repeat('d', 64),
      'aaaaaaaa-4100-0000-0000-000000000001',
      'skipped',
      NULL,
      NULL
    );
    RAISE EXCEPTION 'Conflicting terminal outcome unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'task_already_resolved' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.resolve_task_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-resolve-cross-tenant',
      repeat('e', 64),
      'bbbbbbbb-4000-0000-0000-000000000002',
      'cancelled',
      1,
      NULL
    );
    RAISE EXCEPTION 'Cross-tenant Task resolution unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'task_not_found' THEN
        RAISE;
      END IF;
  END;

  skipped_result := public.resolve_task_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-resolve-skipped',
    repeat('b', 64),
    'aaaaaaaa-4100-0000-0000-000000000002',
    'skipped',
    1,
    NULL
  );
  cancelled_result := public.resolve_task_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-resolve-cancelled',
    repeat('c', 64),
    'aaaaaaaa-4100-0000-0000-000000000003',
    'cancelled',
    1,
    NULL
  );

  IF skipped_result #>> '{task,status}' <> 'skipped'
    OR cancelled_result #>> '{task,status}' <> 'cancelled'
    OR skipped_result ->> 'effect_state' <> 'none'
    OR cancelled_result ->> 'effect_state' <> 'none'
  THEN
    RAISE EXCEPTION 'Skip or Cancel did not produce the canonical terminal state';
  END IF;
END;
$$;

RESET ROLE;
SET ROLE authenticated;

DO $$
BEGIN
  IF has_table_privilege(current_user, 'public.tasks', 'UPDATE')
    OR has_table_privilege(current_user, 'public.tasks', 'DELETE')
    OR has_function_privilege(
      current_user,
      'public.resolve_task_command(uuid,text,text,uuid,task_status,bigint,uuid)',
      'EXECUTE'
    )
  THEN
    RAISE EXCEPTION 'Authenticated role retained Task resolution privileges';
  END IF;
  IF NOT has_table_privilege(current_user, 'public.tasks', 'SELECT') THEN
    RAISE EXCEPTION 'Authenticated role lost Task read access';
  END IF;
END;
$$;

RESET ROLE;
