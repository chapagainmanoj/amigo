# Review: Durable Reminder Outbox Migration 006

Status: approved
Reviewer: project owner
Prepared: 2026-08-30

## Purpose

Issue 05 requires accepted Reminder intent to survive scheduler failure. This migration makes
Reminder lifecycle transitions, Task version changes, command receipts, and stable scheduler
effects one PostgreSQL transaction. The scheduler becomes a rebuildable projection driven by a
backend-only outbox.

Existing Reminder rows receive canonical states and UTC-based intended-time metadata. If legacy
data contains multiple active Reminders for one Task, only the newest remains active; older rows
are preserved as `cancelled` before the unique active-Reminder invariant is installed.

## Proposed migration

```sql
BEGIN;

WITH ranked_active AS (
  SELECT
    reminder_id,
    row_number() OVER (
      PARTITION BY task_id
      ORDER BY scheduled_time DESC, created_at DESC, reminder_id DESC
    ) AS active_rank
  FROM public.reminders
  WHERE status IN ('pending', 'sending', 'sent')
)
UPDATE public.reminders AS reminder
SET status = 'cancelled'
FROM ranked_active
WHERE reminder.reminder_id = ranked_active.reminder_id
  AND ranked_active.active_rank > 1;

CREATE TYPE public.reminder_status AS ENUM (
  'pending',
  'sending',
  'sent',
  'acknowledged',
  'missed',
  'failed',
  'cancelled'
);

DROP INDEX IF EXISTS public.idx_reminders_scheduled;

ALTER TABLE public.reminders
  ALTER COLUMN status DROP DEFAULT;

ALTER TABLE public.reminders
  ALTER COLUMN status TYPE public.reminder_status
  USING (
    CASE status::text
      WHEN 'pending' THEN 'pending'
      WHEN 'sending' THEN 'sending'
      WHEN 'sent' THEN 'sent'
      WHEN 'acknowledged' THEN 'acknowledged'
      WHEN 'missed' THEN 'missed'
      WHEN 'failed' THEN 'failed'
      WHEN 'cancelled' THEN 'cancelled'
      ELSE 'failed'
    END
  )::public.reminder_status;

ALTER TABLE public.reminders
  ALTER COLUMN status SET DEFAULT 'pending'::public.reminder_status,
  ADD COLUMN intended_local_date DATE,
  ADD COLUMN intended_local_time TIME,
  ADD COLUMN intended_timezone TEXT,
  ADD COLUMN version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0);

UPDATE public.reminders
SET
  intended_local_date = (scheduled_time AT TIME ZONE 'UTC')::DATE,
  intended_local_time = (scheduled_time AT TIME ZONE 'UTC')::TIME,
  intended_timezone = 'UTC'
WHERE intended_local_date IS NULL
   OR intended_local_time IS NULL
   OR intended_timezone IS NULL;

ALTER TABLE public.reminders
  ALTER COLUMN intended_local_date SET NOT NULL,
  ALTER COLUMN intended_local_time SET NOT NULL,
  ALTER COLUMN intended_timezone SET NOT NULL;

CREATE UNIQUE INDEX idx_reminders_one_active_per_task
  ON public.reminders(task_id)
  WHERE status IN ('pending', 'sending', 'sent');

CREATE INDEX idx_reminders_scheduled
  ON public.reminders(scheduled_time, status)
  WHERE status = 'pending';

CREATE TYPE public.scheduler_effect_type AS ENUM ('schedule', 'cancel');
CREATE TYPE public.scheduler_outbox_status AS ENUM (
  'pending',
  'processing',
  'completed',
  'failed'
);

CREATE TABLE public.scheduler_outbox (
  effect_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  effect_key TEXT NOT NULL UNIQUE CHECK (length(effect_key) BETWEEN 1 AND 200),
  effect_type public.scheduler_effect_type NOT NULL,
  user_id UUID NOT NULL REFERENCES public.user_profiles(user_id),
  task_id UUID NOT NULL REFERENCES public.tasks(task_id),
  reminder_id UUID NOT NULL REFERENCES public.reminders(reminder_id),
  payload JSONB NOT NULL DEFAULT '{}',
  status public.scheduler_outbox_status NOT NULL DEFAULT 'pending',
  attempts INT NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  worker_id TEXT,
  claimed_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  error_type TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_scheduler_outbox_claim
  ON public.scheduler_outbox(status, available_at, created_at)
  WHERE status IN ('pending', 'processing');

ALTER TABLE public.scheduler_outbox ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.scheduler_outbox FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.scheduler_outbox TO service_role;

REVOKE UPDATE ON TABLE public.reminders FROM authenticated;
DROP POLICY IF EXISTS reminder_update_own ON public.reminders;

CREATE OR REPLACE FUNCTION public.schedule_reminder_command(
  p_user_id UUID,
  p_idempotency_key TEXT,
  p_payload_hash TEXT,
  p_task_id UUID,
  p_replace_reminder_id UUID,
  p_scheduled_time TIMESTAMPTZ,
  p_intended_local_date DATE,
  p_intended_local_time TIME,
  p_intended_timezone TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  existing_receipt public.command_receipts%ROWTYPE;
  task_row public.tasks%ROWTYPE;
  replaced_reminder public.reminders%ROWTYPE;
  active_reminder public.reminders%ROWTYPE;
  created_reminder public.reminders%ROWTYPE;
  telegram_chat_id BIGINT;
  effect_id UUID;
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

  IF p_replace_reminder_id IS NOT NULL THEN
    SELECT reminder.task_id
    INTO p_task_id
    FROM public.reminders AS reminder
    WHERE reminder.reminder_id = p_replace_reminder_id
      AND reminder.user_id = p_user_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'reminder_not_found';
    END IF;
  END IF;

  IF p_task_id IS NULL THEN
    RAISE EXCEPTION 'task_not_found';
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

  IF p_replace_reminder_id IS NOT NULL THEN
    SELECT reminder.*
    INTO replaced_reminder
    FROM public.reminders AS reminder
    WHERE reminder.reminder_id = p_replace_reminder_id
      AND reminder.user_id = p_user_id
      AND reminder.task_id = p_task_id
    FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'reminder_not_found';
    END IF;
    IF replaced_reminder.status NOT IN ('pending', 'sending', 'sent') THEN
      RAISE EXCEPTION 'reminder_not_active';
    END IF;
  END IF;

  IF p_scheduled_time IS NULL OR p_scheduled_time <= now() THEN
    RAISE EXCEPTION 'invalid_scheduled_time';
  END IF;
  IF p_intended_local_date IS NULL
    OR p_intended_local_time IS NULL
    OR p_intended_timezone IS NULL
    OR btrim(p_intended_timezone) = ''
  THEN
    RAISE EXCEPTION 'invalid_intended_time';
  END IF;

  SELECT profile.telegram_chat_id
  INTO telegram_chat_id
  FROM public.user_profiles AS profile
  WHERE profile.user_id = p_user_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'user_not_found';
  END IF;

  FOR active_reminder IN
    SELECT reminder.*
    FROM public.reminders AS reminder
    WHERE reminder.task_id = p_task_id
      AND reminder.user_id = p_user_id
      AND reminder.status IN ('pending', 'sending', 'sent')
    FOR UPDATE
  LOOP
    UPDATE public.reminders
    SET status = 'cancelled', version = version + 1
    WHERE reminder_id = active_reminder.reminder_id;

    INSERT INTO public.scheduler_outbox (
      effect_key,
      effect_type,
      user_id,
      task_id,
      reminder_id,
      payload
    )
    VALUES (
      'cancel:' || active_reminder.reminder_id::text,
      'cancel',
      p_user_id,
      p_task_id,
      active_reminder.reminder_id,
      '{}'::JSONB
    )
    ON CONFLICT (effect_key) DO UPDATE
      SET effect_key = EXCLUDED.effect_key
    RETURNING scheduler_outbox.effect_id INTO effect_id;

    effect_summaries := effect_summaries || jsonb_build_array(
      jsonb_build_object('effect_id', effect_id, 'effect_type', 'cancel')
    );
  END LOOP;

  UPDATE public.tasks
  SET due_date = p_intended_local_date, version = version + 1
  WHERE task_id = p_task_id
  RETURNING * INTO task_row;

  INSERT INTO public.reminders (
    task_id,
    user_id,
    scheduled_time,
    intended_local_date,
    intended_local_time,
    intended_timezone,
    status,
    version
  )
  VALUES (
    p_task_id,
    p_user_id,
    p_scheduled_time,
    p_intended_local_date,
    p_intended_local_time,
    p_intended_timezone,
    'pending',
    1
  )
  RETURNING * INTO created_reminder;

  INSERT INTO public.scheduler_outbox (
    effect_key,
    effect_type,
    user_id,
    task_id,
    reminder_id,
    payload
  )
  VALUES (
    'schedule:' || created_reminder.reminder_id::text,
    'schedule',
    p_user_id,
    p_task_id,
    created_reminder.reminder_id,
    jsonb_build_object(
      'scheduled_time', created_reminder.scheduled_time,
      'telegram_chat_id', telegram_chat_id,
      'task_title', task_row.title
    )
  )
  RETURNING scheduler_outbox.effect_id INTO effect_id;

  effect_summaries := effect_summaries || jsonb_build_array(
    jsonb_build_object('effect_id', effect_id, 'effect_type', 'schedule')
  );

  command_result := jsonb_build_object(
    'reminder', to_jsonb(created_reminder),
    'task_version', task_row.version,
    'scheduled_time', created_reminder.scheduled_time,
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
    CASE
      WHEN p_replace_reminder_id IS NULL THEN 'schedule_reminder'
      ELSE 'reschedule_reminder'
    END,
    p_payload_hash,
    command_result
  );

  RETURN command_result;
END;
$$;

CREATE OR REPLACE FUNCTION public.cancel_reminder_command(
  p_user_id UUID,
  p_idempotency_key TEXT,
  p_payload_hash TEXT,
  p_reminder_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  existing_receipt public.command_receipts%ROWTYPE;
  reminder_row public.reminders%ROWTYPE;
  task_row public.tasks%ROWTYPE;
  owned_task_id UUID;
  effect_id UUID;
  effect_summaries JSONB := '[]'::JSONB;
  effect_state TEXT := 'none';
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
  INTO reminder_row
  FROM public.reminders AS reminder
  WHERE reminder.reminder_id = p_reminder_id
    AND reminder.user_id = p_user_id
    AND reminder.task_id = owned_task_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'reminder_not_found';
  END IF;

  IF reminder_row.status IN ('pending', 'sending', 'sent') THEN
    UPDATE public.reminders
    SET status = 'cancelled', version = version + 1
    WHERE reminder_id = p_reminder_id
    RETURNING * INTO reminder_row;

    UPDATE public.tasks
    SET version = version + 1
    WHERE tasks.task_id = owned_task_id
    RETURNING * INTO task_row;

    INSERT INTO public.scheduler_outbox (
      effect_key,
      effect_type,
      user_id,
      task_id,
      reminder_id,
      payload
    )
    VALUES (
      'cancel:' || p_reminder_id::text,
      'cancel',
      p_user_id,
      owned_task_id,
      p_reminder_id,
      '{}'::JSONB
    )
    ON CONFLICT (effect_key) DO UPDATE
      SET effect_key = EXCLUDED.effect_key
    RETURNING scheduler_outbox.effect_id INTO effect_id;

    effect_summaries := jsonb_build_array(
      jsonb_build_object('effect_id', effect_id, 'effect_type', 'cancel')
    );
    effect_state := 'queued';
  END IF;

  command_result := jsonb_build_object(
    'reminder', to_jsonb(reminder_row),
    'task_version', task_row.version,
    'effect_state', effect_state,
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
    'cancel_reminder',
    p_payload_hash,
    command_result
  );

  RETURN command_result;
END;
$$;

CREATE OR REPLACE FUNCTION public.claim_scheduler_outbox(
  p_limit INT,
  p_worker_id TEXT
)
RETURNS SETOF public.scheduler_outbox
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF p_limit NOT BETWEEN 1 AND 100 OR btrim(COALESCE(p_worker_id, '')) = '' THEN
    RAISE EXCEPTION 'invalid_outbox_claim';
  END IF;

  RETURN QUERY
  WITH candidates AS (
    SELECT effect.effect_id
    FROM public.scheduler_outbox AS effect
    WHERE (
      effect.status = 'pending'
      AND effect.available_at <= now()
    ) OR (
      effect.status = 'processing'
      AND effect.claimed_at < now() - INTERVAL '5 minutes'
    )
    ORDER BY effect.created_at
    LIMIT p_limit
    FOR UPDATE SKIP LOCKED
  )
  UPDATE public.scheduler_outbox AS effect
  SET
    status = 'processing',
    attempts = effect.attempts + 1,
    worker_id = p_worker_id,
    claimed_at = now(),
    error_type = NULL
  FROM candidates
  WHERE effect.effect_id = candidates.effect_id
  RETURNING effect.*;
END;
$$;

CREATE OR REPLACE FUNCTION public.complete_scheduler_outbox(
  p_effect_id UUID,
  p_user_id UUID,
  p_succeeded BOOLEAN,
  p_error_type TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  UPDATE public.scheduler_outbox AS effect
  SET
    status = CASE
      WHEN p_succeeded THEN 'completed'::public.scheduler_outbox_status
      WHEN effect.attempts >= 5 THEN 'failed'::public.scheduler_outbox_status
      ELSE 'pending'::public.scheduler_outbox_status
    END,
    available_at = CASE
      WHEN p_succeeded THEN effect.available_at
      ELSE now() + make_interval(secs => LEAST(60, (2 ^ effect.attempts)::INT))
    END,
    worker_id = NULL,
    claimed_at = NULL,
    completed_at = CASE WHEN p_succeeded THEN now() ELSE NULL END,
    error_type = CASE WHEN p_succeeded THEN NULL ELSE left(p_error_type, 100) END
  WHERE effect.effect_id = p_effect_id
    AND effect.user_id = p_user_id
    AND effect.status = 'processing';

  IF NOT FOUND THEN
    RAISE EXCEPTION 'scheduler_effect_not_found';
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION public.schedule_reminder_command(
  UUID, TEXT, TEXT, UUID, UUID, TIMESTAMPTZ, DATE, TIME, TEXT
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.cancel_reminder_command(
  UUID, TEXT, TEXT, UUID
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_scheduler_outbox(INT, TEXT)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_scheduler_outbox(UUID, UUID, BOOLEAN, TEXT)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.schedule_reminder_command(
  UUID, TEXT, TEXT, UUID, UUID, TIMESTAMPTZ, DATE, TIME, TEXT
) TO service_role;
GRANT EXECUTE ON FUNCTION public.cancel_reminder_command(
  UUID, TEXT, TEXT, UUID
) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_scheduler_outbox(INT, TEXT)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_scheduler_outbox(UUID, UUID, BOOLEAN, TEXT)
  TO service_role;

COMMIT;
```

## Review checklist

- [x] Existing Reminder rows receive safe canonical states and intended-time metadata.
- [x] Duplicate legacy active Reminders are preserved as cancelled before uniqueness is enforced.
- [x] Schedule/reschedule atomically writes Task, Reminder, receipt, and every scheduler effect.
- [x] Cancel records a stable cancellation effect without rewinding terminal Reminder rows.
- [x] Outbox claims are exclusive, reclaim abandoned work, retry with bounds, and retain failures.
- [x] Anonymous/authenticated roles cannot mutate Reminders, inspect outbox rows, or execute RPCs.
- [x] Service functions explicitly verify participant ownership.

## Decision

Approved by the project owner on 2026-08-31.
