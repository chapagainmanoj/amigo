# Review: Atomic Later Command Migration 008

Status: approved
Reviewer: project owner
Prepared: 2026-08-31

## Purpose

Issue 07 requires Telegram and dashboard Later actions to acknowledge the current Reminder, keep
the Task pending, create a policy-defined replacement, persist exact local timing, and queue both
scheduler effects in one transaction. This service-only function enforces ownership, active-state,
version, step, timezone, and one-active-Reminder invariants around that transaction.

## Proposed migration

```sql
BEGIN;

CREATE OR REPLACE FUNCTION public.apply_later_command(
  p_user_id UUID,
  p_idempotency_key TEXT,
  p_payload_hash TEXT,
  p_reminder_id UUID,
  p_expected_task_version BIGINT,
  p_step INT,
  p_scheduled_time TIMESTAMPTZ,
  p_intended_local_date DATE,
  p_intended_local_time TIME,
  p_intended_timezone TEXT,
  p_quiet_hours_adjusted BOOLEAN,
  p_task_due_date DATE
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  existing_receipt public.command_receipts%ROWTYPE;
  owned_task_id UUID;
  user_row public.user_profiles%ROWTYPE;
  task_row public.tasks%ROWTYPE;
  current_reminder public.reminders%ROWTYPE;
  replacement_reminder public.reminders%ROWTYPE;
  cancel_effect_id UUID;
  schedule_effect_id UUID;
  effect_summaries JSONB := '[]'::JSONB;
  command_result JSONB;
BEGIN
  IF p_idempotency_key IS NULL
    OR length(btrim(p_idempotency_key)) NOT BETWEEN 1 AND 200
  THEN
    RAISE EXCEPTION 'invalid_idempotency_key';
  END IF;
  IF p_payload_hash IS NULL OR p_payload_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid_payload_hash';
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

  SELECT reminder.task_id
  INTO owned_task_id
  FROM public.reminders AS reminder
  WHERE reminder.reminder_id = p_reminder_id
    AND reminder.user_id = p_user_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'reminder_not_found';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(owned_task_id::text, 0));

  SELECT profile.*
  INTO user_row
  FROM public.user_profiles AS profile
  WHERE profile.user_id = p_user_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'user_not_found';
  END IF;

  SELECT task.*
  INTO task_row
  FROM public.tasks AS task
  WHERE task.task_id = owned_task_id
    AND task.user_id = p_user_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'reminder_not_found';
  END IF;

  SELECT reminder.*
  INTO current_reminder
  FROM public.reminders AS reminder
  WHERE reminder.reminder_id = p_reminder_id
    AND reminder.task_id = owned_task_id
    AND reminder.user_id = p_user_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'reminder_not_found';
  END IF;

  IF task_row.status <> 'pending' THEN
    RAISE EXCEPTION 'task_not_pending';
  END IF;
  IF current_reminder.status NOT IN ('pending', 'sending', 'sent') THEN
    RAISE EXCEPTION 'reminder_not_active';
  END IF;
  IF p_expected_task_version IS NOT NULL
    AND task_row.version <> p_expected_task_version
  THEN
    RAISE EXCEPTION 'stale_task_version';
  END IF;
  IF p_step IS NULL OR p_step <> current_reminder.snooze_count + 1 THEN
    RAISE EXCEPTION 'later_step_stale';
  END IF;
  IF p_scheduled_time IS NULL OR p_scheduled_time <= now() THEN
    RAISE EXCEPTION 'invalid_scheduled_time';
  END IF;
  IF p_intended_local_date IS NULL
    OR p_intended_local_time IS NULL
    OR btrim(COALESCE(p_intended_timezone, '')) = ''
    OR p_intended_timezone <> COALESCE(user_row.timezone, 'UTC')
  THEN
    RAISE EXCEPTION 'invalid_intended_time';
  END IF;
  IF (p_scheduled_time AT TIME ZONE p_intended_timezone)::DATE
      <> p_intended_local_date
    OR (p_scheduled_time AT TIME ZONE p_intended_timezone)::TIME
      <> p_intended_local_time
  THEN
    RAISE EXCEPTION 'intended_time_mismatch';
  END IF;
  IF p_step >= 3 AND (
    p_task_due_date IS NULL
    OR p_task_due_date <> p_intended_local_date
    OR p_task_due_date <= (now() AT TIME ZONE p_intended_timezone)::DATE
  ) THEN
    RAISE EXCEPTION 'invalid_next_planning_day';
  END IF;
  IF p_step < 3 AND p_task_due_date IS NOT NULL THEN
    RAISE EXCEPTION 'unexpected_planning_day_change';
  END IF;

  UPDATE public.reminders
  SET
    status = 'acknowledged',
    version = version + 1
  WHERE reminder_id = p_reminder_id
  RETURNING * INTO current_reminder;

  UPDATE public.tasks
  SET
    due_date = COALESCE(p_task_due_date, due_date),
    deferred_count = deferred_count + 1,
    version = version + 1
  WHERE task_id = owned_task_id
  RETURNING * INTO task_row;

  INSERT INTO public.reminders (
    task_id,
    user_id,
    scheduled_time,
    intended_local_date,
    intended_local_time,
    intended_timezone,
    status,
    snooze_count,
    version
  )
  VALUES (
    owned_task_id,
    p_user_id,
    p_scheduled_time,
    p_intended_local_date,
    p_intended_local_time,
    p_intended_timezone,
    'pending',
    p_step,
    1
  )
  RETURNING * INTO replacement_reminder;

  INSERT INTO public.scheduler_outbox (
    effect_key,
    effect_type,
    user_id,
    task_id,
    reminder_id,
    payload
  )
  VALUES (
    'cancel:' || current_reminder.reminder_id::text,
    'cancel',
    p_user_id,
    owned_task_id,
    current_reminder.reminder_id,
    '{}'::JSONB
  )
  ON CONFLICT (effect_key) DO UPDATE
    SET effect_key = EXCLUDED.effect_key
  RETURNING scheduler_outbox.effect_id INTO cancel_effect_id;

  effect_summaries := effect_summaries || jsonb_build_array(
    jsonb_build_object('effect_id', cancel_effect_id, 'effect_type', 'cancel')
  );

  INSERT INTO public.scheduler_outbox (
    effect_key,
    effect_type,
    user_id,
    task_id,
    reminder_id,
    payload
  )
  VALUES (
    'schedule:' || replacement_reminder.reminder_id::text,
    'schedule',
    p_user_id,
    owned_task_id,
    replacement_reminder.reminder_id,
    jsonb_build_object(
      'scheduled_time', replacement_reminder.scheduled_time,
      'telegram_chat_id', user_row.telegram_chat_id,
      'task_title', task_row.title
    )
  )
  RETURNING scheduler_outbox.effect_id INTO schedule_effect_id;

  effect_summaries := effect_summaries || jsonb_build_array(
    jsonb_build_object('effect_id', schedule_effect_id, 'effect_type', 'schedule')
  );

  command_result := jsonb_build_object(
    'task', to_jsonb(task_row),
    'task_version', task_row.version,
    'acknowledged_reminder', to_jsonb(current_reminder),
    'reminder', to_jsonb(replacement_reminder),
    'scheduled_time', replacement_reminder.scheduled_time,
    'intended_local_date', replacement_reminder.intended_local_date,
    'intended_local_time', replacement_reminder.intended_local_time,
    'intended_timezone', replacement_reminder.intended_timezone,
    'later_step', p_step,
    'quiet_hours_adjusted', p_quiet_hours_adjusted,
    'effect_state', 'queued',
    'effects', effect_summaries
  );

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
    'apply_later',
    p_payload_hash,
    command_result
  );

  RETURN command_result;
END;
$$;

REVOKE ALL ON FUNCTION public.apply_later_command(
  UUID, TEXT, TEXT, UUID, BIGINT, INT, TIMESTAMPTZ, DATE, TIME, TEXT, BOOLEAN, DATE
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.apply_later_command(
  UUID, TEXT, TEXT, UUID, BIGINT, INT, TIMESTAMPTZ, DATE, TIME, TEXT, BOOLEAN, DATE
) TO service_role;

COMMIT;
```

## Review checklist

- [x] Matching replay returns the stored result before re-evaluating mutable Reminder state.
- [x] The current active Reminder becomes acknowledged and is never rewound.
- [x] The pending replacement carries the next snooze step and exact local/UTC timing.
- [x] Third-and-later actions move the Task to the replacement's future Planning Day.
- [x] Task/Reminder versions, deferral count, receipt, and both scheduler effects are atomic.
- [x] Stale versions, stale steps, terminal Tasks/Reminders, and wrong-owner IDs fail closed.
- [x] Intended local timing matches the UTC instant and the participant's stored timezone.
- [x] Anonymous/authenticated roles cannot execute the service-only function.

## Decision

Approved by the project owner on 2026-08-31.
