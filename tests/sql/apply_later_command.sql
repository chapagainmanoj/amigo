\set ON_ERROR_STOP on

INSERT INTO public.tasks(task_id, user_id, title, status, due_date)
VALUES (
  'aaaaaaaa-4200-0000-0000-000000000001',
  'aaaaaaaa-0000-0000-0000-000000000001',
  'Apply Later sequence',
  'pending',
  (now() AT TIME ZONE 'UTC')::DATE
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
  'aaaaaaaa-5200-0000-0000-000000000001',
  'aaaaaaaa-4200-0000-0000-000000000001',
  'aaaaaaaa-0000-0000-0000-000000000001',
  now() + INTERVAL '1 minute',
  'sent',
  (now() AT TIME ZONE 'UTC')::DATE,
  (now() AT TIME ZONE 'UTC')::TIME,
  'UTC'
);

SET ROLE service_role;

DO $$
DECLARE
  first_result JSONB;
  replay_result JSONB;
  second_result JSONB;
  third_result JSONB;
  first_replacement UUID;
  second_replacement UUID;
  first_time TIMESTAMPTZ := now() + INTERVAL '1 hour';
  second_time TIMESTAMPTZ := now() + INTERVAL '2 hours';
  third_date DATE := (now() AT TIME ZONE 'UTC')::DATE + 1;
  third_time TIMESTAMPTZ;
BEGIN
  third_time := (third_date + TIME '07:30:00') AT TIME ZONE 'UTC';

  first_result := public.apply_later_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-later-1',
    repeat('a', 64),
    'aaaaaaaa-5200-0000-0000-000000000001',
    1,
    1,
    first_time,
    (first_time AT TIME ZONE 'UTC')::DATE,
    (first_time AT TIME ZONE 'UTC')::TIME,
    'UTC',
    FALSE,
    NULL
  );
  replay_result := public.apply_later_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-later-1',
    repeat('a', 64),
    'aaaaaaaa-5200-0000-0000-000000000001',
    1,
    1,
    first_time,
    (first_time AT TIME ZONE 'UTC')::DATE,
    (first_time AT TIME ZONE 'UTC')::TIME,
    'UTC',
    FALSE,
    NULL
  );

  IF replay_result <> first_result
    OR first_result #>> '{acknowledged_reminder,status}' <> 'acknowledged'
    OR first_result #>> '{reminder,status}' <> 'pending'
    OR first_result ->> 'later_step' <> '1'
    OR first_result ->> 'task_version' <> '2'
    OR jsonb_array_length(first_result -> 'effects') <> 2
  THEN
    RAISE EXCEPTION 'First Later or exact replay failed';
  END IF;

  BEGIN
    PERFORM public.apply_later_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-later-1',
      repeat('f', 64),
      'aaaaaaaa-5200-0000-0000-000000000001',
      1,
      1,
      first_time,
      (first_time AT TIME ZONE 'UTC')::DATE,
      (first_time AT TIME ZONE 'UTC')::TIME,
      'UTC',
      FALSE,
      NULL
    );
    RAISE EXCEPTION 'Conflicting Later payload unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'idempotency_key_conflict' THEN
        RAISE;
      END IF;
  END;

  first_replacement := (first_result #>> '{reminder,reminder_id}')::UUID;

  BEGIN
    PERFORM public.apply_later_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-later-stale-version',
      repeat('d', 64),
      first_replacement,
      1,
      2,
      second_time,
      (second_time AT TIME ZONE 'UTC')::DATE,
      (second_time AT TIME ZONE 'UTC')::TIME,
      'UTC',
      FALSE,
      NULL
    );
    RAISE EXCEPTION 'Stale Later Task version unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'stale_task_version' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.apply_later_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-later-stale-step',
      repeat('e', 64),
      first_replacement,
      2,
      99,
      second_time,
      (second_time AT TIME ZONE 'UTC')::DATE,
      (second_time AT TIME ZONE 'UTC')::TIME,
      'UTC',
      FALSE,
      NULL
    );
    RAISE EXCEPTION 'Stale Later step unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'later_step_stale' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.apply_later_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-later-cross-tenant',
      repeat('e', 64),
      'bbbbbbbb-5000-0000-0000-000000000002',
      NULL,
      1,
      first_time,
      (first_time AT TIME ZONE 'UTC')::DATE,
      (first_time AT TIME ZONE 'UTC')::TIME,
      'UTC',
      FALSE,
      NULL
    );
    RAISE EXCEPTION 'Cross-tenant Later unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'reminder_not_found' THEN
        RAISE;
      END IF;
  END;

  UPDATE public.reminders
  SET status = 'sent'
  WHERE reminder_id = first_replacement;

  second_result := public.apply_later_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-later-2',
    repeat('b', 64),
    first_replacement,
    2,
    2,
    second_time,
    (second_time AT TIME ZONE 'UTC')::DATE,
    (second_time AT TIME ZONE 'UTC')::TIME,
    'UTC',
    FALSE,
    NULL
  );
  second_replacement := (second_result #>> '{reminder,reminder_id}')::UUID;

  UPDATE public.reminders
  SET status = 'sent'
  WHERE reminder_id = second_replacement;

  third_result := public.apply_later_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-later-3',
    repeat('c', 64),
    second_replacement,
    3,
    3,
    third_time,
    third_date,
    TIME '07:30:00',
    'UTC',
    FALSE,
    third_date
  );

  IF second_result ->> 'later_step' <> '2'
    OR third_result ->> 'later_step' <> '3'
    OR third_result #>> '{task,due_date}' <> third_date::TEXT
    OR third_result #>> '{task,status}' <> 'pending'
    OR third_result #>> '{task,deferred_count}' <> '3'
    OR (
      SELECT count(*)
      FROM public.reminders
      WHERE task_id = 'aaaaaaaa-4200-0000-0000-000000000001'
        AND status IN ('pending', 'sending', 'sent')
    ) <> 1
    OR (
      SELECT count(*)
      FROM public.scheduler_outbox
      WHERE task_id = 'aaaaaaaa-4200-0000-0000-000000000001'
    ) <> 6
  THEN
    RAISE EXCEPTION 'Later sequence did not preserve canonical state';
  END IF;
END;
$$;

RESET ROLE;
SET ROLE authenticated;

DO $$
BEGIN
  IF has_function_privilege(
    current_user,
    'public.apply_later_command(uuid,text,text,uuid,bigint,integer,timestamptz,date,time,text,boolean,date)',
    'EXECUTE'
  ) THEN
    RAISE EXCEPTION 'Authenticated role can execute Apply Later';
  END IF;
END;
$$;

RESET ROLE;
