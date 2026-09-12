\set ON_ERROR_STOP on

SET ROLE service_role;

DO $$
DECLARE
  journey JSONB;
  replay JSONB;
  profile JSONB;
  test_result JSONB;
  state JSONB;
  v_reminder_id UUID;
  v_task_id UUID;
  v_updated_at TIMESTAMPTZ;
  i INT;
BEGIN
  -- Pairing is gated on an acknowledged Activation Journey.
  BEGIN
    PERFORM public.issue_pairing_token(
      repeat('a', 32),
      'aaaaaaaa-1111-1111-1111-111111111111',
      now() + INTERVAL '10 minutes'
    );
    RAISE EXCEPTION 'Pairing token issued without an acknowledged Activation Journey';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'activation_not_acknowledged' THEN
        RAISE;
      END IF;
  END;

  -- The profile cannot be set before the limits are acknowledged.
  BEGIN
    PERFORM public.update_activation_profile(
      'aaaaaaaa-1111-1111-1111-111111111111', 'Participant A', 'America/Toronto',
      TIME '07:00', TIME '22:30'
    );
    RAISE EXCEPTION 'Activation profile accepted before acknowledgement';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'activation_not_acknowledged' THEN
        RAISE;
      END IF;
  END;

  journey := public.acknowledge_activation_terms(
    'aaaaaaaa-1111-1111-1111-111111111111', '2026-08-29'
  );
  replay := public.acknowledge_activation_terms(
    'aaaaaaaa-1111-1111-1111-111111111111', '2026-08-29'
  );

  IF replay <> journey
    OR journey ->> 'policy_version' <> '2026-08-29'
    OR journey ->> 'acknowledged_at' IS NULL
    OR journey ->> 'version' <> '1'
  THEN
    RAISE EXCEPTION 'Acknowledgement is not immutable and idempotent';
  END IF;

  -- A different policy version must not silently overwrite the acknowledgement.
  BEGIN
    PERFORM public.acknowledge_activation_terms(
      'aaaaaaaa-1111-1111-1111-111111111111', '2099-01-01'
    );
    RAISE EXCEPTION 'A superseding policy version was silently accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'activation_policy_superseded' THEN
        RAISE;
      END IF;
  END;

  -- Pairing now succeeds for the acknowledged identity.
  PERFORM public.issue_pairing_token(
    repeat('a', 32),
    'aaaaaaaa-1111-1111-1111-111111111111',
    now() + INTERVAL '10 minutes'
  );

  state := public.get_activation_state('aaaaaaaa-1111-1111-1111-111111111111');
  IF state ->> 'step' <> 'profile'
    OR state #>> '{pairing,status}' <> 'active'
    OR (state ->> 'paired')::BOOLEAN IS NOT TRUE
  THEN
    RAISE EXCEPTION 'Activation state did not report an active pairing for a paired account';
  END IF;

  -- The API normalizes the name; the database stores what it is given, matching
  -- InMemoryStore and FakeStore, and validates rather than silently rewriting.
  BEGIN
    PERFORM public.update_activation_profile(
      'aaaaaaaa-1111-1111-1111-111111111111', '   ', 'America/Toronto',
      TIME '07:00', TIME '22:30'
    );
    RAISE EXCEPTION 'A blank Activation name was accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'invalid_activation_name' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.update_activation_profile(
      'aaaaaaaa-1111-1111-1111-111111111111', 'Jo' || chr(1) || 'e', 'America/Toronto',
      TIME '07:00', TIME '22:30'
    );
    RAISE EXCEPTION 'A control character in the Activation name was accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'invalid_activation_name' THEN
        RAISE;
      END IF;
  END;

  profile := public.update_activation_profile(
    'aaaaaaaa-1111-1111-1111-111111111111', 'Participant A', 'America/Toronto',
    TIME '07:00', TIME '22:30'
  );

  state := public.get_activation_state('aaaaaaaa-1111-1111-1111-111111111111');
  IF state #>> '{profile,wake_time}' <> '07:00'
    OR state #>> '{profile,sleep_time}' <> '22:30'
  THEN
    RAISE EXCEPTION 'Activation profile did not expose HH:MM quiet hours';
  END IF;

  IF profile #>> '{profile,name}' <> 'Participant A'
    OR profile #>> '{profile,timezone}' <> 'America/Toronto'
    OR profile #>> '{profile,onboarding_step}' <> '3'
    OR profile #>> '{journey,profile_completed_at}' IS NULL
    OR profile #>> '{journey,version}' <> '2'
  THEN
    RAISE EXCEPTION 'Activation profile did not normalize and advance durable progress';
  END IF;

  -- Re-applying the profile must not advance the journey version again.
  profile := public.update_activation_profile(
    'aaaaaaaa-1111-1111-1111-111111111111', 'Participant A', 'America/Toronto',
    TIME '07:00', TIME '22:30'
  );
  IF profile #>> '{journey,version}' <> '2' THEN
    RAISE EXCEPTION 'Repeating the profile step advanced the journey version';
  END IF;

  -- Equal wake and quiet-hour times are rejected.
  BEGIN
    PERFORM public.update_activation_profile(
      'aaaaaaaa-1111-1111-1111-111111111111', 'Participant A', 'America/Toronto',
      TIME '07:00', TIME '07:00'
    );
    RAISE EXCEPTION 'Equal wake and sleep times were accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'invalid_activation_quiet_hours' THEN
        RAISE;
      END IF;
  END;

  -- The test Reminder timezone must match the stored Activation profile.
  BEGIN
    PERFORM public.create_activation_test_command(
      'aaaaaaaa-0000-0000-0000-000000000001', 'sql-activation-tz', repeat('b', 64),
      'Private Amigo test reminder', FALSE, now() + INTERVAL '2 minutes',
      current_date, TIME '12:00', 'Asia/Kathmandu'
    );
    RAISE EXCEPTION 'A mismatched test Reminder timezone was accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'activation_timezone_mismatch' THEN
        RAISE;
      END IF;
  END;

  test_result := public.create_activation_test_command(
    'aaaaaaaa-0000-0000-0000-000000000001', 'sql-activation-test', repeat('c', 64),
    'Private Amigo test reminder', FALSE, now() + INTERVAL '2 minutes',
    current_date, TIME '12:00', 'America/Toronto'
  );

  IF test_result ->> 'effect_state' <> 'queued'
    OR jsonb_array_length(test_result -> 'effects') <> 1
    OR test_result #>> '{effects,0,effect_type}' <> 'schedule'
    OR test_result #>> '{reminder,status}' <> 'pending'
    OR test_result #>> '{reminder,evidence_class}' <> 'participant'
    OR test_result #>> '{task,version}' <> '2'
    OR test_result ->> 'journey_version' <> '3'
  THEN
    RAISE EXCEPTION 'The Activation test command did not produce its canonical result';
  END IF;

  -- Within one transaction `now()` is fixed, so this block can only prove the command
  -- stamps the journey's audit fields together. Advancement across commands is proved by
  -- the separate top-level block at the end of this file, which runs in its own
  -- transaction and therefore sees a later `now()`.
  SELECT updated_at INTO v_updated_at
  FROM public.activation_journeys
  WHERE auth_id = 'aaaaaaaa-1111-1111-1111-111111111111';
  IF v_updated_at IS NULL
    OR v_updated_at <> (
      SELECT test_confirmed_at FROM public.activation_journeys
      WHERE auth_id = 'aaaaaaaa-1111-1111-1111-111111111111'
    )
  THEN
    RAISE EXCEPTION 'The Activation test command did not stamp the journey audit fields';
  END IF;

  v_task_id := (test_result #>> '{task,task_id}')::UUID;
  v_reminder_id := (test_result #>> '{reminder,reminder_id}')::UUID;

  -- Migration 011 captures the occurrence by trigger; the command must not duplicate it.
  IF (
    SELECT count(*) FROM public.reminder_occurrences WHERE reminder_id = v_reminder_id
  ) <> 1 THEN
    RAISE EXCEPTION 'Activation test Reminder did not capture exactly one occurrence';
  END IF;

  -- Replay returns the stored receipt without creating a second Reminder.
  IF public.create_activation_test_command(
    'aaaaaaaa-0000-0000-0000-000000000001', 'sql-activation-test', repeat('c', 64),
    'Private Amigo test reminder', FALSE, now() + INTERVAL '2 minutes',
    current_date, TIME '12:00', 'America/Toronto'
  ) <> test_result THEN
    RAISE EXCEPTION 'Replayed Activation test command did not return its receipt';
  END IF;

  IF (
    SELECT count(*) FROM public.reminders WHERE task_id = v_task_id
  ) <> 1 THEN
    RAISE EXCEPTION 'Replayed Activation test command created a second Reminder';
  END IF;

  -- The profile locks once the test exists.
  BEGIN
    PERFORM public.update_activation_profile(
      'aaaaaaaa-1111-1111-1111-111111111111', 'Participant A', 'America/Toronto',
      TIME '06:00', TIME '21:00'
    );
    RAISE EXCEPTION 'Activation profile was editable after the test was scheduled';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'activation_profile_locked' THEN
        RAISE;
      END IF;
  END;

  -- A second, non-retry test is refused.
  BEGIN
    PERFORM public.create_activation_test_command(
      'aaaaaaaa-0000-0000-0000-000000000001', 'sql-activation-second', repeat('d', 64),
      'Private Amigo test reminder', FALSE, now() + INTERVAL '2 minutes',
      current_date, TIME '12:00', 'America/Toronto'
    );
    RAISE EXCEPTION 'A second Activation test Reminder was accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'activation_test_exists' THEN
        RAISE;
      END IF;
  END;

  -- A retry of a healthy, not-yet-late Reminder is refused.
  BEGIN
    PERFORM public.create_activation_test_command(
      'aaaaaaaa-0000-0000-0000-000000000001', 'sql-activation-early-retry', repeat('e', 64),
      'Private Amigo test reminder', TRUE, now() + INTERVAL '2 minutes',
      current_date, TIME '12:00', 'America/Toronto'
    );
    RAISE EXCEPTION 'A retry of a healthy Activation Reminder was accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'activation_retry_not_allowed' THEN
        RAISE;
      END IF;
  END;

  -- A failed Reminder becomes retryable, cancels nothing extra, and queues one schedule.
  UPDATE public.reminders SET status = 'failed' WHERE reminder_id = v_reminder_id;

  state := public.get_activation_state('aaaaaaaa-1111-1111-1111-111111111111');
  IF state #>> '{test,delivery_state}' <> 'failed'
    OR (state #>> '{test,can_retry}')::BOOLEAN IS NOT TRUE
    OR state ->> 'step' <> 'resolve'
  THEN
    RAISE EXCEPTION 'A failed Activation Reminder was not reported as retryable';
  END IF;

  test_result := public.create_activation_test_command(
    'aaaaaaaa-0000-0000-0000-000000000001', 'sql-activation-retry', repeat('f', 64),
    'Private Amigo test reminder', TRUE, now() + INTERVAL '3 minutes',
    current_date, TIME '12:05', 'America/Toronto'
  );

  IF jsonb_array_length(test_result -> 'effects') <> 1
    OR test_result #>> '{effects,0,effect_type}' <> 'schedule'
    OR (test_result #>> '{reminder,reminder_id}')::UUID = v_reminder_id
    OR (test_result #>> '{task,task_id}')::UUID <> v_task_id
  THEN
    RAISE EXCEPTION 'The Activation retry did not replace the Reminder on the same Task';
  END IF;

  -- Completion is finalized only from durable delivery and resolution evidence.
  UPDATE public.reminders
  SET telegram_message_id = 4242, status = 'acknowledged'
  WHERE reminder_id = (test_result #>> '{reminder,reminder_id}')::UUID;
  UPDATE public.tasks SET status = 'completed' WHERE task_id = v_task_id;

  state := public.get_activation_state('aaaaaaaa-1111-1111-1111-111111111111');
  IF state ->> 'step' <> 'dashboard'
    OR (state ->> 'completed')::BOOLEAN IS NOT TRUE
    OR state ->> 'completed_at' IS NULL
    OR state #>> '{test,resolution}' <> 'done'
    OR NOT EXISTS (
      SELECT 1 FROM public.user_profiles
      WHERE user_id = 'aaaaaaaa-0000-0000-0000-000000000001'
        AND onboarding_complete
    )
  THEN
    RAISE EXCEPTION 'Activation completion was not finalized from canonical evidence';
  END IF;

  -- Finalization is idempotent: re-reading must not advance the journey again.
  IF public.get_activation_state('aaaaaaaa-1111-1111-1111-111111111111') ->> 'journey_version'
     <> state ->> 'journey_version'
  THEN
    RAISE EXCEPTION 'Re-reading a completed Activation Journey advanced its version';
  END IF;

  -- A different participant never sees this journey.
  IF public.get_activation_state('bbbbbbbb-2222-2222-2222-222222222222') ->> 'step' <> 'limits'
  THEN
    RAISE EXCEPTION 'Activation state leaked across participants';
  END IF;

  -- A journey pointing at another participant's Task must never reach that Task.
  UPDATE public.activation_journeys
  SET test_task_id = 'bbbbbbbb-4000-0000-0000-000000000002', test_reminder_id = NULL
  WHERE auth_id = 'aaaaaaaa-1111-1111-1111-111111111111';

  test_result := public.create_activation_test_command(
    'aaaaaaaa-0000-0000-0000-000000000001', 'sql-activation-cross-tenant', repeat('7', 64),
    'Private Amigo test reminder', FALSE, now() + INTERVAL '2 minutes',
    current_date, TIME '12:00', 'America/Toronto'
  );

  IF (test_result #>> '{task,task_id}')::UUID = 'bbbbbbbb-4000-0000-0000-000000000002'
    OR (test_result #>> '{task,user_id}')::UUID <> 'aaaaaaaa-0000-0000-0000-000000000001'
  THEN
    RAISE EXCEPTION 'The Activation test command reached another participant''s Task';
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.tasks
    WHERE task_id = 'bbbbbbbb-4000-0000-0000-000000000002'
      AND version <> 1
  ) THEN
    RAISE EXCEPTION 'The Activation test command mutated another participant''s Task';
  END IF;

  -- Restore participant A's own test Task before the remaining assertions.
  UPDATE public.activation_journeys
  SET test_task_id = v_task_id, test_reminder_id = v_reminder_id
  WHERE auth_id = 'aaaaaaaa-1111-1111-1111-111111111111';

  -- Replacing issue_pairing_token must preserve its rate limit, not just its gate.
  PERFORM public.acknowledge_activation_terms(
    'cccccccc-3333-3333-3333-333333333333', '2026-08-29'
  );
  FOR i IN 1..5 LOOP
    PERFORM public.issue_pairing_token(
      lpad(to_hex(i), 32, '0'),
      'cccccccc-3333-3333-3333-333333333333',
      now() + INTERVAL '10 minutes'
    );
  END LOOP;
  BEGIN
    PERFORM public.issue_pairing_token(
      lpad(to_hex(6), 32, '0'),
      'cccccccc-3333-3333-3333-333333333333',
      now() + INTERVAL '10 minutes'
    );
    RAISE EXCEPTION 'The pairing token rate limit was not preserved';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'pairing_token_rate_limited' THEN
        RAISE;
      END IF;
  END;

  -- A reused idempotency key with different input must fail closed.
  BEGIN
    PERFORM public.create_activation_test_command(
      'aaaaaaaa-0000-0000-0000-000000000001', 'sql-activation-test', repeat('9', 64),
      'Private Amigo test reminder', TRUE, now() + INTERVAL '4 minutes',
      current_date, TIME '12:10', 'America/Toronto'
    );
    RAISE EXCEPTION 'A conflicting Activation idempotency payload was accepted';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'idempotency_key_conflict' THEN
        RAISE;
      END IF;
  END;

  -- Resolution alone never completes Activation: delivery evidence is required.
  PERFORM public.acknowledge_activation_terms(
    'bbbbbbbb-2222-2222-2222-222222222222', '2026-08-29'
  );
  PERFORM public.update_activation_profile(
    'bbbbbbbb-2222-2222-2222-222222222222', 'Participant B', 'America/Toronto',
    TIME '07:00', TIME '22:30'
  );
  test_result := public.create_activation_test_command(
    'bbbbbbbb-0000-0000-0000-000000000002', 'sql-activation-undelivered', repeat('1', 64),
    'Private Amigo test reminder', FALSE, now() + INTERVAL '2 minutes',
    current_date, TIME '12:00', 'America/Toronto'
  );

  v_reminder_id := (test_result #>> '{reminder,reminder_id}')::UUID;
  v_task_id := (test_result #>> '{task,task_id}')::UUID;

  -- A resolved Task whose Reminder was never acknowledged is not a resolution.
  UPDATE public.tasks SET status = 'completed' WHERE task_id = v_task_id;

  state := public.get_activation_state('bbbbbbbb-2222-2222-2222-222222222222');
  IF state #>> '{test,resolution}' IS NOT NULL
    OR state #>> '{test,delivery_state}' <> 'scheduled'
    OR (state ->> 'completed')::BOOLEAN IS NOT FALSE
  THEN
    RAISE EXCEPTION 'Task status alone was treated as an Activation resolution';
  END IF;

  -- A pending Reminder past its scheduled instant is late and retryable.
  UPDATE public.reminders
  SET scheduled_time = now() - INTERVAL '2 minutes'
  WHERE reminder_id = v_reminder_id;

  state := public.get_activation_state('bbbbbbbb-2222-2222-2222-222222222222');
  IF state #>> '{test,delivery_state}' <> 'late'
    OR (state #>> '{test,can_retry}')::BOOLEAN IS NOT TRUE
  THEN
    RAISE EXCEPTION 'An overdue pending Activation Reminder was not reported late';
  END IF;

  UPDATE public.reminders
  SET status = 'acknowledged'
  WHERE reminder_id = v_reminder_id;

  state := public.get_activation_state('bbbbbbbb-2222-2222-2222-222222222222');
  IF (state ->> 'completed')::BOOLEAN IS NOT FALSE
    OR state ->> 'step' <> 'resolve'
    OR state ->> 'completed_at' IS NOT NULL
    OR (state #>> '{test,delivered}')::BOOLEAN IS NOT FALSE
    OR state #>> '{test,resolution}' <> 'done'
    OR EXISTS (
      SELECT 1 FROM public.user_profiles
      WHERE user_id = 'bbbbbbbb-0000-0000-0000-000000000002'
        AND onboarding_complete
    )
  THEN
    RAISE EXCEPTION 'Activation completed without durable delivery evidence';
  END IF;

  -- Provider acceptance recorded on the occurrence is delivery evidence in its own
  -- right, even when no Telegram message id was captured on the Reminder.
  UPDATE public.reminder_occurrences
  SET first_claimed_at = now(), provider_accepted_at = now()
  WHERE reminder_id = v_reminder_id;

  state := public.get_activation_state('bbbbbbbb-2222-2222-2222-222222222222');
  IF (state #>> '{test,delivered}')::BOOLEAN IS NOT TRUE
    OR (state ->> 'completed')::BOOLEAN IS NOT TRUE
    OR state ->> 'step' <> 'dashboard'
    OR EXISTS (
      SELECT 1 FROM public.reminders
      WHERE reminder_id = v_reminder_id AND telegram_message_id IS NOT NULL
    )
  THEN
    RAISE EXCEPTION 'Provider acceptance was not accepted as Activation delivery evidence';
  END IF;
END;
$$;

DO $$
DECLARE
  definer BOOLEAN;
  config TEXT[];
  name TEXT;
BEGIN
  FOREACH name IN ARRAY ARRAY[
    'acknowledge_activation_terms',
    'update_activation_profile',
    'create_activation_test_command',
    'get_activation_state'
  ]
  LOOP
    SELECT proc.prosecdef, proc.proconfig
    INTO definer, config
    FROM pg_catalog.pg_proc AS proc
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = proc.pronamespace
    WHERE namespace.nspname = 'public'
      AND proc.proname = name;

    IF NOT FOUND OR NOT definer THEN
      RAISE EXCEPTION 'Activation function % is not SECURITY DEFINER', name;
    END IF;
    IF config IS NULL
      OR NOT ('search_path=pg_catalog, public' = ANY(config))
      OR NOT ('TimeZone=UTC' = ANY(config))
    THEN
      RAISE EXCEPTION 'Activation function % did not pin search_path and UTC', name;
    END IF;
  END LOOP;
END;
$$;

-- Each top-level statement below is its own transaction, so `now()` advances between
-- them. This is what proves the test command stamps a NEW updated_at rather than
-- leaving the journey's audit trail at its previous value.

CREATE TEMP TABLE activation_updated_probe AS
SELECT auth_id, updated_at, version
FROM public.activation_journeys
WHERE auth_id = 'bbbbbbbb-2222-2222-2222-222222222222';

DO $$
BEGIN
  UPDATE public.reminders
  SET status = 'cancelled'
  WHERE reminder_id = (
    SELECT test_reminder_id FROM public.activation_journeys
    WHERE auth_id = 'bbbbbbbb-2222-2222-2222-222222222222'
  );
END;
$$;

DO $$
BEGIN
  PERFORM public.create_activation_test_command(
    'bbbbbbbb-0000-0000-0000-000000000002', 'sql-activation-updated-at', repeat('3', 64),
    'Private Amigo test reminder', TRUE, now() + INTERVAL '3 minutes',
    current_date, TIME '12:20', 'America/Toronto'
  );
END;
$$;

DO $$
DECLARE
  before_updated TIMESTAMPTZ;
  before_version BIGINT;
  after_updated TIMESTAMPTZ;
  after_version BIGINT;
BEGIN
  SELECT updated_at, version INTO before_updated, before_version
  FROM activation_updated_probe;
  SELECT updated_at, version INTO after_updated, after_version
  FROM public.activation_journeys
  WHERE auth_id = 'bbbbbbbb-2222-2222-2222-222222222222';

  IF after_updated IS NULL OR after_updated <= before_updated THEN
    RAISE EXCEPTION
      'The Activation test command did not advance the journey updated_at (% -> %)',
      before_updated, after_updated;
  END IF;
  IF after_version <> before_version + 1 THEN
    RAISE EXCEPTION 'The Activation retry did not advance the journey version exactly once';
  END IF;
END;
$$;

DROP TABLE activation_updated_probe;

RESET ROLE;
SET ROLE anon;

DO $$
BEGIN
  IF has_table_privilege(current_user, 'public.activation_journeys', 'SELECT')
    OR has_function_privilege(current_user, 'public.get_activation_state(uuid)', 'EXECUTE')
    OR has_function_privilege(
      current_user,
      'public.acknowledge_activation_terms(uuid,text)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.update_activation_profile(uuid,text,text,time,time)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.create_activation_test_command(uuid,text,text,text,boolean,'
      || 'timestamp with time zone,date,time without time zone,text)',
      'EXECUTE'
    )
  THEN
    RAISE EXCEPTION 'Anonymous role retained Activation access';
  END IF;
END;
$$;

RESET ROLE;
SET ROLE authenticated;

DO $$
BEGIN
  IF has_table_privilege(current_user, 'public.activation_journeys', 'SELECT')
    OR has_function_privilege(current_user, 'public.get_activation_state(uuid)', 'EXECUTE')
    OR has_function_privilege(
      current_user,
      'public.acknowledge_activation_terms(uuid,text)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.update_activation_profile(uuid,text,text,time,time)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.create_activation_test_command(uuid,text,text,text,boolean,'
      || 'timestamp with time zone,date,time without time zone,text)',
      'EXECUTE'
    )
  THEN
    RAISE EXCEPTION 'Authenticated role retained Activation access';
  END IF;
END;
$$;

RESET ROLE;
