-- Channel identities, step 2 (ADR 0004). Producers stop carrying the participant's Telegram address:
-- delivery resolves the primary channel's recipient at fire time, so the scheduler-outbox payload key
-- `telegram_chat_id` and the handoff listing's column were only legacy hints.
-- The three producers below are copied verbatim from 006, 008 and 013 minus that one payload line.
-- Kept for later: the telegram_chat_id column, its mirror trigger and the v1 Telegram RPCs.
BEGIN;
DO $$ BEGIN
 IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 22) <> 22
 OR (SELECT max(version) FROM public.schema_migrations) <> 22 THEN
 RAISE EXCEPTION '023 requires the complete approved 001-022 chain'; END IF;
END $$;

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

CREATE OR REPLACE FUNCTION public.create_activation_test_command(
  p_user_id UUID,
  p_idempotency_key TEXT,
  p_payload_hash TEXT,
  p_title TEXT,
  p_retry BOOLEAN,
  p_scheduled_time TIMESTAMPTZ,
  p_intended_local_date DATE,
  p_intended_local_time TIME,
  p_intended_timezone TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
SET timezone = 'UTC'
AS $$
DECLARE
  existing_receipt public.command_receipts%ROWTYPE;
  profile_row public.user_profiles%ROWTYPE;
  observed_auth_id UUID;
  journey_row public.activation_journeys%ROWTYPE;
  task_row public.tasks%ROWTYPE;
  replaced_reminder public.reminders%ROWTYPE;
  reminder_row public.reminders%ROWTYPE;
  effect_id UUID;
  effect_summaries JSONB := '[]'::JSONB;
  retryable BOOLEAN;
  moment TIMESTAMPTZ := now();
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
  IF p_title IS NULL OR length(btrim(p_title)) NOT BETWEEN 1 AND 200 THEN
    RAISE EXCEPTION 'invalid_task_title';
  END IF;
  IF p_scheduled_time IS NULL
    OR p_intended_local_date IS NULL
    OR p_intended_local_time IS NULL
    OR p_intended_timezone IS NULL
  THEN
    RAISE EXCEPTION 'invalid_scheduled_time';
  END IF;

  -- Single lock order for every Activation function: the identity's advisory lock is
  -- taken first, before any other advisory or row lock. Taking the receipt lock or a
  -- user_profiles row lock ahead of it creates a cycle with a concurrent
  -- get_activation_state, which deadlocks the dashboard against this command.
  SELECT profile.*
  INTO profile_row
  FROM public.user_profiles AS profile
  WHERE profile.user_id = p_user_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'user_not_found';
  END IF;

  -- The identity the advisory key below is derived from. Only a change to *this* value
  -- between the unlocked read and the row lock means the key went stale.
  observed_auth_id := profile_row.supabase_auth_id;

  PERFORM pg_advisory_xact_lock(
    hashtextextended(COALESCE(profile_row.supabase_auth_id::text, p_user_id::text), 0)
  );

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

  -- Row-lock order is activation_journeys before user_profiles, matching
  -- get_activation_state. The advisory key above is derived from an unlocked read, so
  -- a concurrent complete_pairing setting supabase_auth_id can make that key stale;
  -- a fixed row-lock order keeps this safe even when the two sides disagree on the key.
  SELECT journey.*
  INTO journey_row
  FROM public.activation_journeys AS journey
  WHERE journey.auth_id = profile_row.supabase_auth_id
  FOR UPDATE;

  SELECT profile.*
  INTO profile_row
  FROM public.user_profiles AS profile
  WHERE profile.user_id = p_user_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'user_not_found';
  END IF;

  -- Re-verify the identity under the row lock: complete_pairing may have set
  -- supabase_auth_id since the unlocked read that chose both the advisory key and the
  -- journey row above. Taking a second activation_journeys lock here would invert the
  -- order this function just established and deadlock against get_activation_state,
  -- which locks journeys first. The identity changed underneath this transaction, so the
  -- correct answer is to abandon it and let the caller retry under the now-correct key.
  IF observed_auth_id IS DISTINCT FROM profile_row.supabase_auth_id THEN
    RAISE EXCEPTION 'activation_pairing_changed';
  END IF;

  IF journey_row.auth_id IS NULL OR journey_row.profile_completed_at IS NULL THEN
    RAISE EXCEPTION 'activation_profile_incomplete';
  END IF;

  IF profile_row.timezone IS DISTINCT FROM p_intended_timezone THEN
    RAISE EXCEPTION 'activation_timezone_mismatch';
  END IF;

  IF journey_row.test_task_id IS NOT NULL THEN
    SELECT task.*
    INTO task_row
    FROM public.tasks AS task
    WHERE task.task_id = journey_row.test_task_id
      AND task.user_id = p_user_id
    FOR UPDATE;
  END IF;

  IF task_row.task_id IS NOT NULL THEN
    IF NOT COALESCE(p_retry, FALSE) THEN
      RAISE EXCEPTION 'activation_test_exists';
    END IF;

    IF journey_row.test_reminder_id IS NOT NULL THEN
      SELECT reminder.*
      INTO replaced_reminder
      FROM public.reminders AS reminder
      WHERE reminder.reminder_id = journey_row.test_reminder_id
        AND reminder.user_id = p_user_id
      FOR UPDATE;
    END IF;

    retryable := replaced_reminder.reminder_id IS NOT NULL
      AND (
        replaced_reminder.status IN ('failed', 'missed', 'cancelled')
        OR (
          replaced_reminder.status = 'pending'
          AND replaced_reminder.telegram_message_id IS NULL
          AND moment > replaced_reminder.scheduled_time + INTERVAL '30 seconds'
        )
      );

    IF NOT retryable THEN
      RAISE EXCEPTION 'activation_retry_not_allowed';
    END IF;

    IF replaced_reminder.status IN ('pending', 'sending', 'sent') THEN
      UPDATE public.reminders
      SET status = 'cancelled', version = version + 1
      WHERE reminder_id = replaced_reminder.reminder_id;

      INSERT INTO public.scheduler_outbox (
        effect_key, effect_type, user_id, task_id, reminder_id, payload
      )
      VALUES (
        'cancel:' || replaced_reminder.reminder_id::text,
        'cancel',
        p_user_id,
        task_row.task_id,
        replaced_reminder.reminder_id,
        '{}'::JSONB
      )
      ON CONFLICT (effect_key) DO UPDATE
        SET effect_key = EXCLUDED.effect_key
      RETURNING scheduler_outbox.effect_id INTO effect_id;

      effect_summaries := effect_summaries || jsonb_build_array(
        jsonb_build_object('effect_id', effect_id, 'effect_type', 'cancel')
      );
    END IF;
  ELSE
    INSERT INTO public.tasks (
      user_id, title, category, due_date, status, created_date, created_at
    )
    VALUES (
      p_user_id,
      btrim(p_title),
      'other',
      p_intended_local_date,
      'pending',
      p_intended_local_date,
      moment
    )
    RETURNING * INTO task_row;
  END IF;

  INSERT INTO public.reminders (
    task_id,
    user_id,
    scheduled_time,
    status,
    intended_local_date,
    intended_local_time,
    intended_timezone,
    evidence_class,
    created_at
  )
  VALUES (
    task_row.task_id,
    p_user_id,
    p_scheduled_time,
    'pending',
    p_intended_local_date,
    p_intended_local_time,
    p_intended_timezone,
    'participant',
    moment
  )
  RETURNING * INTO reminder_row;

  UPDATE public.tasks
  SET due_date = p_intended_local_date, version = version + 1
  WHERE task_id = task_row.task_id
  RETURNING * INTO task_row;

  INSERT INTO public.scheduler_outbox (
    effect_key, effect_type, user_id, task_id, reminder_id, payload
  )
  VALUES (
    'schedule:' || reminder_row.reminder_id::text,
    'schedule',
    p_user_id,
    task_row.task_id,
    reminder_row.reminder_id,
    jsonb_build_object(
      'scheduled_time', to_jsonb(p_scheduled_time),
      'task_title', task_row.title
    )
  )
  RETURNING scheduler_outbox.effect_id INTO effect_id;

  effect_summaries := effect_summaries || jsonb_build_array(
    jsonb_build_object('effect_id', effect_id, 'effect_type', 'schedule')
  );

  UPDATE public.activation_journeys
  SET
    test_task_id = task_row.task_id,
    test_reminder_id = reminder_row.reminder_id,
    test_confirmed_at = moment,
    completed_at = NULL,
    version = journey_row.version + 1,
    updated_at = moment
  WHERE auth_id = journey_row.auth_id
  RETURNING * INTO journey_row;

  command_result := jsonb_build_object(
    'task', to_jsonb(task_row),
    'reminder', to_jsonb(reminder_row),
    'effect_state', 'queued',
    'effects', effect_summaries,
    'journey_version', journey_row.version
  );

  INSERT INTO public.command_receipts (
    user_id, idempotency_key, command_type, payload_hash, result
  )
  VALUES (
    p_user_id,
    p_idempotency_key,
    'create_activation_test',
    p_payload_hash,
    command_result
  );

  RETURN command_result;
END;
$$;

DROP FUNCTION public.list_pending_handoff_executions(INT);
CREATE FUNCTION public.list_pending_handoff_executions(p_limit INT DEFAULT 25)
RETURNS TABLE(user_id UUID, handoff_id UUID, execution_session_id UUID, target_mode_id TEXT)
LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
  SELECT h.user_id, h.handoff_id, h.execution_session_id, h.target_mode_id
  FROM public.mode_handoffs h
  WHERE h.resolution='confirmed' AND h.executed_at IS NULL AND h.execution_failed_at IS NULL
    AND (h.execution_claimed_at IS NULL OR h.execution_claimed_at <= clock_timestamp()-interval '5 minutes')
  ORDER BY h.created_at LIMIT greatest(1, least(p_limit,100));
$$;
REVOKE ALL ON FUNCTION public.list_pending_handoff_executions(INT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.list_pending_handoff_executions(INT) TO service_role;

DO $$ BEGIN
 IF EXISTS (
   SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname = 'public'
     AND p.proname IN ('schedule_reminder_command', 'apply_later_command',
                       'create_activation_test_command')
     AND p.prosrc LIKE '%''telegram_chat_id''%')
 OR (SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public'
       AND p.proname IN ('schedule_reminder_command', 'apply_later_command',
                         'create_activation_test_command')) <> 3
 OR to_regprocedure('public.list_pending_handoff_executions(integer)') IS NULL
 OR (SELECT 'telegram_chat_id' = ANY(proargnames) FROM pg_catalog.pg_proc
   WHERE oid = 'public.list_pending_handoff_executions(integer)'::regprocedure)
 OR has_function_privilege('authenticated', 'public.list_pending_handoff_executions(integer)', 'EXECUTE')
 THEN RAISE EXCEPTION '023 producers still carry telegram_chat_id'; END IF;
 INSERT INTO public.schema_migrations(version) VALUES(23);
END $$;
COMMIT;
