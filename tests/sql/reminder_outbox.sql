\set ON_ERROR_STOP on

SET ROLE service_role;

DO $$
DECLARE
  first_result JSONB;
  replay_result JSONB;
  reschedule_result JSONB;
  cancel_result JSONB;
  first_reminder_id UUID;
  replacement_reminder_id UUID;
  first_scheduled_time TIMESTAMPTZ := now() + INTERVAL '3 hours';
  replacement_scheduled_time TIMESTAMPTZ := now() + INTERVAL '4 hours';
  claimed public.scheduler_outbox%ROWTYPE;
  claimed_count INTEGER := 0;
BEGIN
  first_result := public.schedule_reminder_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-schedule-reminder-1',
    repeat('d', 64),
    'aaaaaaaa-4000-0000-0000-000000000001',
    NULL,
    first_scheduled_time,
    (now() AT TIME ZONE 'Asia/Kathmandu')::DATE,
    TIME '09:30:00',
    'Asia/Kathmandu'
  );
  replay_result := public.schedule_reminder_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-schedule-reminder-1',
    repeat('d', 64),
    'aaaaaaaa-4000-0000-0000-000000000001',
    NULL,
    first_scheduled_time,
    (now() AT TIME ZONE 'Asia/Kathmandu')::DATE,
    TIME '09:30:00',
    'Asia/Kathmandu'
  );

  IF replay_result <> first_result THEN
    RAISE EXCEPTION 'Schedule Reminder replay did not return the stored result';
  END IF;
  IF first_result ->> 'effect_state' <> 'queued'
    OR jsonb_array_length(first_result -> 'effects') <> 2
    OR first_result #>> '{reminder,intended_timezone}' <> 'Asia/Kathmandu'
  THEN
    RAISE EXCEPTION 'Schedule Reminder did not return its exact queued intent';
  END IF;

  first_reminder_id := (first_result #>> '{reminder,reminder_id}')::UUID;

  IF (
    SELECT count(*)
    FROM public.reminders
    WHERE task_id = 'aaaaaaaa-4000-0000-0000-000000000001'
      AND status IN ('pending', 'sending', 'sent')
  ) <> 1 THEN
    RAISE EXCEPTION 'Schedule Reminder violated one-active-Reminder invariant';
  END IF;

  BEGIN
    PERFORM public.schedule_reminder_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-cross-tenant-reminder',
      repeat('e', 64),
      'bbbbbbbb-4000-0000-0000-000000000002',
      NULL,
      now() + INTERVAL '5 hours',
      current_date,
      TIME '10:00:00',
      'UTC'
    );
    RAISE EXCEPTION 'Cross-tenant Reminder schedule unexpectedly succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'task_not_found' THEN
        RAISE;
      END IF;
  END;

  reschedule_result := public.schedule_reminder_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-reschedule-reminder-1',
    repeat('e', 64),
    NULL,
    first_reminder_id,
    replacement_scheduled_time,
    (now() AT TIME ZONE 'Asia/Kathmandu')::DATE,
    TIME '10:30:00',
    'Asia/Kathmandu'
  );
  replacement_reminder_id := (reschedule_result #>> '{reminder,reminder_id}')::UUID;

  IF replacement_reminder_id = first_reminder_id
    OR reschedule_result ->> 'effect_state' <> 'queued'
    OR jsonb_array_length(reschedule_result -> 'effects') <> 2
    OR (
      SELECT status
      FROM public.reminders
      WHERE reminder_id = first_reminder_id
    ) <> 'cancelled'
  THEN
    RAISE EXCEPTION 'Reschedule did not cancel and replace the active Reminder';
  END IF;

  cancel_result := public.cancel_reminder_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-cancel-reminder-1',
    repeat('f', 64),
    replacement_reminder_id
  );
  replay_result := public.cancel_reminder_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-cancel-reminder-1',
    repeat('f', 64),
    replacement_reminder_id
  );

  IF replay_result <> cancel_result
    OR cancel_result ->> 'effect_state' <> 'queued'
    OR jsonb_array_length(cancel_result -> 'effects') <> 1
    OR cancel_result #>> '{reminder,status}' <> 'cancelled'
  THEN
    RAISE EXCEPTION 'Cancel Reminder did not return stable queued state';
  END IF;

  IF (
    SELECT count(*)
    FROM public.scheduler_outbox
    WHERE user_id = 'aaaaaaaa-0000-0000-0000-000000000001'
  ) <> 5 OR (
    SELECT count(DISTINCT effect_key)
    FROM public.scheduler_outbox
    WHERE user_id = 'aaaaaaaa-0000-0000-0000-000000000001'
  ) <> 5 THEN
    RAISE EXCEPTION 'Reminder commands did not retain five stable scheduler effects';
  END IF;

  IF (
    SELECT count(*)
    FROM public.command_receipts
    WHERE idempotency_key IN (
      'sql-schedule-reminder-1',
      'sql-reschedule-reminder-1',
      'sql-cancel-reminder-1'
    )
  ) <> 3 THEN
    RAISE EXCEPTION 'Reminder command replay created invalid receipt population';
  END IF;

  IF (cancel_result ->> 'task_version')::BIGINT <> (
    SELECT version
    FROM public.tasks
    WHERE task_id = 'aaaaaaaa-4000-0000-0000-000000000001'
  ) THEN
    RAISE EXCEPTION 'Reminder result did not expose the committed Task version';
  END IF;

  FOR claimed IN
    SELECT *
    FROM public.claim_scheduler_outbox(100, 'sql-worker')
  LOOP
    claimed_count := claimed_count + 1;
    IF claimed.status <> 'processing'
      OR claimed.attempts <> 1
      OR claimed.worker_id <> 'sql-worker'
    THEN
      RAISE EXCEPTION 'Scheduler effect claim was not exclusive processing state';
    END IF;
    PERFORM public.complete_scheduler_outbox(
      claimed.effect_id,
      claimed.user_id,
      TRUE,
      NULL
    );
  END LOOP;

  IF claimed_count <> 5 OR EXISTS (
    SELECT 1
    FROM public.scheduler_outbox
    WHERE status <> 'completed'
  ) THEN
    RAISE EXCEPTION 'Scheduler outbox did not drain all durable effects';
  END IF;
END;
$$;

RESET ROLE;
SET ROLE authenticated;

DO $$
BEGIN
  IF has_table_privilege(current_user, 'public.reminders', 'UPDATE')
    OR has_table_privilege(current_user, 'public.scheduler_outbox', 'SELECT')
    OR has_function_privilege(
      current_user,
      'public.schedule_reminder_command(uuid,text,text,uuid,uuid,timestamptz,date,time,text)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.cancel_reminder_command(uuid,text,text,uuid)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.claim_scheduler_outbox(integer,text)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.complete_scheduler_outbox(uuid,uuid,boolean,text)',
      'EXECUTE'
    )
  THEN
    RAISE EXCEPTION 'Authenticated role retained a Reminder command boundary privilege';
  END IF;
END;
$$;

RESET ROLE;
