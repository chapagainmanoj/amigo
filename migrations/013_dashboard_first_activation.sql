BEGIN;

CREATE TABLE public.activation_journeys (
  auth_id UUID PRIMARY KEY,
  policy_version TEXT NOT NULL CHECK (length(btrim(policy_version)) BETWEEN 1 AND 40),
  acknowledged_at TIMESTAMPTZ NOT NULL,
  profile_completed_at TIMESTAMPTZ,
  test_task_id UUID REFERENCES public.tasks(task_id),
  test_reminder_id UUID REFERENCES public.reminders(reminder_id),
  test_confirmed_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.activation_journeys ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.activation_journeys FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.activation_journeys TO service_role;

-- ── Pairing requires an acknowledged Activation Journey ──

CREATE OR REPLACE FUNCTION public.issue_pairing_token(
  p_token TEXT,
  p_auth_id UUID,
  p_expires_at TIMESTAMPTZ
)
RETURNS SETOF public.pairing_tokens
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_now TIMESTAMPTZ := now();
  v_recent_count INTEGER;
  v_token public.pairing_tokens%ROWTYPE;
BEGIN
  IF p_token !~ '^[0-9a-f]{32}$' THEN
    RAISE EXCEPTION 'pairing_token_invalid_format' USING ERRCODE = 'P0001';
  END IF;

  IF p_expires_at <= v_now OR p_expires_at > v_now + INTERVAL '15 minutes' THEN
    RAISE EXCEPTION 'pairing_token_invalid_expiry' USING ERRCODE = 'P0001';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM public.activation_journeys AS journey
    WHERE journey.auth_id = p_auth_id
      AND journey.acknowledged_at IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'activation_not_acknowledged' USING ERRCODE = 'P0001';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_auth_id::TEXT, 0));

  SELECT count(*)
  INTO v_recent_count
  FROM public.pairing_tokens
  WHERE supabase_auth_id = p_auth_id
    AND created_at >= v_now - INTERVAL '15 minutes';

  IF v_recent_count >= 5 THEN
    RAISE EXCEPTION 'pairing_token_rate_limited' USING ERRCODE = 'P0001';
  END IF;

  UPDATE public.pairing_tokens
  SET invalidated_at = v_now
  WHERE supabase_auth_id = p_auth_id
    AND consumed = FALSE
    AND invalidated_at IS NULL;

  DELETE FROM public.pairing_tokens
  WHERE supabase_auth_id = p_auth_id
    AND expires_at < v_now - INTERVAL '24 hours';

  INSERT INTO public.pairing_tokens(token, supabase_auth_id, created_at, expires_at)
  VALUES (p_token, p_auth_id, v_now, p_expires_at)
  RETURNING * INTO v_token;

  RETURN NEXT v_token;
END;
$$;

-- ── Immutable policy acknowledgement ──

CREATE OR REPLACE FUNCTION public.acknowledge_activation_terms(
  p_auth_id UUID,
  p_policy_version TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
SET timezone = 'UTC'
AS $$
DECLARE
  journey_row public.activation_journeys%ROWTYPE;
  moment TIMESTAMPTZ := now();
BEGIN
  IF p_auth_id IS NULL THEN
    RAISE EXCEPTION 'invalid_auth_id';
  END IF;
  IF p_policy_version IS NULL
    OR length(btrim(p_policy_version)) NOT BETWEEN 1 AND 40
  THEN
    RAISE EXCEPTION 'invalid_policy_version';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_auth_id::text, 0));

  SELECT journey.*
  INTO journey_row
  FROM public.activation_journeys AS journey
  WHERE journey.auth_id = p_auth_id
  FOR UPDATE;

  IF FOUND THEN
    IF journey_row.policy_version <> p_policy_version THEN
      RAISE EXCEPTION 'activation_policy_superseded';
    END IF;
    RETURN to_jsonb(journey_row);
  END IF;

  INSERT INTO public.activation_journeys (
    auth_id,
    policy_version,
    acknowledged_at,
    version,
    created_at,
    updated_at
  )
  VALUES (p_auth_id, p_policy_version, moment, 1, moment, moment)
  RETURNING * INTO journey_row;

  RETURN to_jsonb(journey_row);
END;
$$;

-- ── Paired profile and durable journey progress ──

CREATE OR REPLACE FUNCTION public.update_activation_profile(
  p_auth_id UUID,
  p_name TEXT,
  p_timezone TEXT,
  p_wake_time TIME,
  p_sleep_time TIME
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
SET timezone = 'UTC'
AS $$
DECLARE
  journey_row public.activation_journeys%ROWTYPE;
  profile_row public.user_profiles%ROWTYPE;
  moment TIMESTAMPTZ := now();
BEGIN
  IF p_auth_id IS NULL THEN
    RAISE EXCEPTION 'invalid_auth_id';
  END IF;
  IF p_name IS NULL
    OR length(btrim(p_name)) NOT BETWEEN 1 AND 80
    OR p_name ~ '[\x00-\x1f]'
  THEN
    RAISE EXCEPTION 'invalid_activation_name';
  END IF;
  IF p_timezone IS NULL OR length(btrim(p_timezone)) < 1 THEN
    RAISE EXCEPTION 'invalid_activation_timezone';
  END IF;
  IF p_wake_time IS NULL OR p_sleep_time IS NULL OR p_wake_time = p_sleep_time THEN
    RAISE EXCEPTION 'invalid_activation_quiet_hours';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_auth_id::text, 0));

  SELECT journey.*
  INTO journey_row
  FROM public.activation_journeys AS journey
  WHERE journey.auth_id = p_auth_id
  FOR UPDATE;

  IF NOT FOUND OR journey_row.acknowledged_at IS NULL THEN
    RAISE EXCEPTION 'activation_not_acknowledged';
  END IF;

  IF journey_row.test_task_id IS NOT NULL THEN
    RAISE EXCEPTION 'activation_profile_locked';
  END IF;

  SELECT profile.*
  INTO profile_row
  FROM public.user_profiles AS profile
  WHERE profile.supabase_auth_id = p_auth_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'activation_not_paired';
  END IF;

  UPDATE public.user_profiles
  SET
    name = p_name,
    timezone = p_timezone,
    wake_time = p_wake_time,
    sleep_time = p_sleep_time,
    onboarding_step = 3,
    onboarding_complete = FALSE,
    updated_at = moment
  WHERE user_id = profile_row.user_id
  RETURNING * INTO profile_row;

  UPDATE public.activation_journeys
  SET
    profile_completed_at = COALESCE(journey_row.profile_completed_at, moment),
    version = CASE
      WHEN journey_row.profile_completed_at IS NULL THEN journey_row.version + 1
      ELSE journey_row.version
    END,
    updated_at = moment
  WHERE auth_id = p_auth_id
  RETURNING * INTO journey_row;

  RETURN jsonb_build_object(
    'journey', to_jsonb(journey_row),
    'profile', to_jsonb(profile_row)
  );
END;
$$;

-- ── Combined private test Task, Reminder, receipt, and scheduler effects ──

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

  -- Re-verify the identity under the row lock: it may have been paired since the
  -- unlocked read that chose the advisory key.
  IF journey_row.auth_id IS DISTINCT FROM profile_row.supabase_auth_id THEN
    SELECT journey.*
    INTO journey_row
    FROM public.activation_journeys AS journey
    WHERE journey.auth_id = profile_row.supabase_auth_id
    FOR UPDATE;
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
      'telegram_chat_id', profile_row.telegram_chat_id,
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

-- ── Canonical Activation read model, finalized only from durable evidence ──

CREATE OR REPLACE FUNCTION public.get_activation_state(p_auth_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
SET timezone = 'UTC'
AS $$
DECLARE
  journey_row public.activation_journeys%ROWTYPE;
  profile_row public.user_profiles%ROWTYPE;
  token_row public.pairing_tokens%ROWTYPE;
  task_row public.tasks%ROWTYPE;
  reminder_row public.reminders%ROWTYPE;
  occurrence_row public.reminder_occurrences%ROWTYPE;
  moment TIMESTAMPTZ := now();
  acknowledged BOOLEAN;
  profile_complete BOOLEAN;
  paired BOOLEAN;
  pairing_status TEXT := 'none';
  delivered BOOLEAN := FALSE;
  resolution TEXT;
  delivery_state TEXT := 'not_scheduled';
  can_retry BOOLEAN := FALSE;
  complete BOOLEAN;
  step TEXT;
BEGIN
  IF p_auth_id IS NULL THEN
    RAISE EXCEPTION 'invalid_auth_id';
  END IF;

  -- The advisory lock is the mutex for one identity's Activation Journey, and every
  -- function here takes it before any row lock so the finalizing UPDATEs below cannot
  -- deadlock against a concurrent create_activation_test_command.
  PERFORM pg_advisory_xact_lock(hashtextextended(p_auth_id::text, 0));

  SELECT journey.* INTO journey_row
  FROM public.activation_journeys AS journey
  WHERE journey.auth_id = p_auth_id
  FOR UPDATE;

  SELECT profile.* INTO profile_row
  FROM public.user_profiles AS profile
  WHERE profile.supabase_auth_id = p_auth_id
  FOR UPDATE;

  SELECT token.* INTO token_row
  FROM public.pairing_tokens AS token
  WHERE token.supabase_auth_id = p_auth_id
  ORDER BY token.created_at DESC
  LIMIT 1;

  IF journey_row.test_task_id IS NOT NULL THEN
    SELECT task.* INTO task_row
    FROM public.tasks AS task
    WHERE task.task_id = journey_row.test_task_id;
  END IF;

  IF journey_row.test_reminder_id IS NOT NULL THEN
    SELECT reminder.* INTO reminder_row
    FROM public.reminders AS reminder
    WHERE reminder.reminder_id = journey_row.test_reminder_id;
  END IF;

  IF reminder_row.reminder_id IS NOT NULL THEN
    SELECT occurrence.* INTO occurrence_row
    FROM public.reminder_occurrences AS occurrence
    WHERE occurrence.reminder_id = reminder_row.reminder_id;
  END IF;

  acknowledged := journey_row.acknowledged_at IS NOT NULL;
  paired := profile_row.user_id IS NOT NULL;
  profile_complete := journey_row.profile_completed_at IS NOT NULL AND paired;

  IF token_row.token IS NOT NULL THEN
    IF token_row.invalidated_at IS NOT NULL THEN
      pairing_status := 'replaced';
    ELSIF token_row.consumed THEN
      pairing_status := 'used';
    ELSIF token_row.expires_at <= moment THEN
      pairing_status := 'expired';
    ELSE
      pairing_status := 'active';
    END IF;
  END IF;

  IF reminder_row.reminder_id IS NOT NULL THEN
    delivered := reminder_row.telegram_message_id IS NOT NULL
      OR occurrence_row.provider_accepted_at IS NOT NULL;
  END IF;

  IF task_row.task_id IS NOT NULL AND reminder_row.reminder_id IS NOT NULL THEN
    IF task_row.status = 'completed' AND reminder_row.status = 'acknowledged' THEN
      resolution := 'done';
    ELSIF task_row.status = 'skipped' AND reminder_row.status = 'acknowledged' THEN
      resolution := 'skip';
    ELSIF reminder_row.status = 'acknowledged'
      AND task_row.status = 'pending'
      AND COALESCE(task_row.deferred_count, 0) > 0
    THEN
      resolution := 'later';
    END IF;
  END IF;

  IF reminder_row.reminder_id IS NOT NULL THEN
    IF delivered THEN
      delivery_state := 'delivered';
    ELSIF reminder_row.status = 'failed' THEN
      delivery_state := 'failed';
      can_retry := TRUE;
    ELSIF reminder_row.status = 'missed' THEN
      delivery_state := 'missed';
      can_retry := TRUE;
    ELSIF reminder_row.status = 'cancelled' THEN
      delivery_state := 'cancelled';
      can_retry := TRUE;
    ELSIF reminder_row.status = 'pending'
      AND moment > reminder_row.scheduled_time + INTERVAL '30 seconds'
    THEN
      delivery_state := 'late';
      can_retry := TRUE;
    ELSE
      delivery_state := 'scheduled';
    END IF;
  END IF;

  complete := delivered AND COALESCE(resolution IN ('done', 'skip', 'later'), FALSE);

  IF complete AND journey_row.auth_id IS NOT NULL AND journey_row.completed_at IS NULL THEN
    UPDATE public.activation_journeys
    SET completed_at = moment, updated_at = moment, version = version + 1
    WHERE auth_id = p_auth_id
    RETURNING * INTO journey_row;
  END IF;

  IF complete AND paired AND NOT COALESCE(profile_row.onboarding_complete, FALSE) THEN
    UPDATE public.user_profiles
    SET onboarding_complete = TRUE, updated_at = moment
    WHERE user_id = profile_row.user_id
    RETURNING * INTO profile_row;
  END IF;

  IF NOT acknowledged THEN
    step := 'limits';
  ELSIF NOT paired THEN
    step := 'telegram';
  ELSIF NOT profile_complete THEN
    step := 'profile';
  ELSIF reminder_row.reminder_id IS NULL THEN
    step := 'test_reminder';
  ELSIF NOT complete THEN
    step := 'resolve';
  ELSE
    step := 'dashboard';
  END IF;

  RETURN jsonb_build_object(
    'policy_version', to_jsonb(journey_row.policy_version),
    'acknowledged_at', to_jsonb(journey_row.acknowledged_at),
    'journey_version', COALESCE(journey_row.version, 0),
    'step', step,
    'completed', complete,
    'completed_at', to_jsonb(journey_row.completed_at),
    'paired', paired,
    'pairing', jsonb_build_object(
      'status', pairing_status,
      'expires_at', to_jsonb(token_row.expires_at)
    ),
    'profile_complete', profile_complete,
    'profile', CASE
      WHEN paired THEN jsonb_build_object(
        'name', to_jsonb(profile_row.name),
        'timezone', to_jsonb(profile_row.timezone),
        'wake_time', to_jsonb(to_char(profile_row.wake_time, 'HH24:MI')),
        'sleep_time', to_jsonb(to_char(profile_row.sleep_time, 'HH24:MI'))
      )
      ELSE 'null'::JSONB
    END,
    'test', jsonb_build_object(
      'task', CASE
        WHEN task_row.task_id IS NOT NULL THEN jsonb_build_object(
          'title', to_jsonb(task_row.title),
          'status', to_jsonb(task_row.status),
          'due_date', to_jsonb(task_row.due_date),
          'version', to_jsonb(task_row.version),
          'deferred_count', COALESCE(task_row.deferred_count, 0)
        )
        ELSE 'null'::JSONB
      END,
      'reminder', CASE
        WHEN reminder_row.reminder_id IS NOT NULL THEN jsonb_build_object(
          'scheduled_time', to_jsonb(reminder_row.scheduled_time),
          'intended_local_date', to_jsonb(reminder_row.intended_local_date),
          'intended_local_time', to_jsonb(
            to_char(reminder_row.intended_local_time, 'HH24:MI:SS')
          ),
          'intended_timezone', to_jsonb(reminder_row.intended_timezone),
          'status', to_jsonb(reminder_row.status)
        )
        ELSE 'null'::JSONB
      END,
      'delivered', delivered,
      'delivery_state', delivery_state,
      'resolution', to_jsonb(resolution),
      'can_retry', can_retry
    ),
    'generated_at', to_jsonb(moment)
  );
END;
$$;

-- ── Service-only access ──

REVOKE ALL ON FUNCTION public.acknowledge_activation_terms(UUID, TEXT)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.update_activation_profile(UUID, TEXT, TEXT, TIME, TIME)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.create_activation_test_command(
  UUID, TEXT, TEXT, TEXT, BOOLEAN, TIMESTAMPTZ, DATE, TIME, TEXT
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_activation_state(UUID)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.acknowledge_activation_terms(UUID, TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.update_activation_profile(UUID, TEXT, TEXT, TIME, TIME)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.create_activation_test_command(
  UUID, TEXT, TEXT, TEXT, BOOLEAN, TIMESTAMPTZ, DATE, TIME, TEXT
) TO service_role;
GRANT EXECUTE ON FUNCTION public.get_activation_state(UUID) TO service_role;

COMMIT;
