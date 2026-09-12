DO $$
DECLARE
  legacy_count INT;
  success_claim JSONB;
  failure_claim JSONB;
  success_attempt UUID;
  failure_attempt UUID;
  success_reminder UUID := '44444444-4444-4444-8444-444444444444';
  failure_reminder UUID := '55555555-5555-4555-8555-555555555555';
  health JSONB;
BEGIN
  SELECT count(*) INTO legacy_count
  FROM public.reminder_occurrences
  WHERE reminder_id = '33333333-3333-4333-8333-333333333333'
    AND measurable = false
    AND unmeasurable_reason = 'pre_instrumentation';
  IF legacy_count <> 1 THEN
    RAISE EXCEPTION 'legacy occurrence was not explicitly marked unmeasurable';
  END IF;

  INSERT INTO public.tasks (task_id, user_id, title, status)
  VALUES (
    '66666666-6666-4666-8666-666666666666',
    '11111111-1111-4111-8111-111111111111',
    'Synthetic success',
    'pending'
  );
  INSERT INTO public.reminders (
    reminder_id, task_id, user_id, scheduled_time, status,
    intended_local_date, intended_local_time, intended_timezone, evidence_class
  ) VALUES (
    success_reminder,
    '66666666-6666-4666-8666-666666666666',
    '11111111-1111-4111-8111-111111111111',
    now() - interval '1 minute',
    'pending',
    current_date,
    localtime,
    'UTC',
    'staging_synthetic'
  );

  success_claim := public.claim_reminder_delivery(
    success_reminder,
    '11111111-1111-4111-8111-111111111111',
    'delivery-success-1'
  );
  IF NOT (success_claim ->> 'claimed')::BOOLEAN THEN
    RAISE EXCEPTION 'success reminder was not claimed';
  END IF;
  success_attempt := success_claim #>> '{attempt,attempt_id}';
  PERFORM public.finish_reminder_delivery(
    success_attempt,
    success_reminder,
    '11111111-1111-4111-8111-111111111111',
    'accepted',
    NULL,
    'do_not_retry',
    9911
  );
  UPDATE public.reminders SET status = 'acknowledged'
  WHERE reminder_id = success_reminder;

  IF NOT EXISTS (
    SELECT 1 FROM public.reminder_occurrences
    WHERE reminder_id = success_reminder
      AND evidence_class = 'staging_synthetic'
      AND confirmed_at IS NOT NULL
      AND first_claimed_at IS NOT NULL
      AND provider_accepted_at IS NOT NULL
      AND terminal_at IS NOT NULL
      AND acknowledged_at IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'successful occurrence timestamps are incomplete';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM public.reminder_delivery_attempts
    WHERE attempt_id = success_attempt
      AND result = 'accepted'
      AND retry_decision = 'do_not_retry'
      AND provider_latency_ms IS NOT NULL
  ) THEN
    RAISE EXCEPTION 'successful attempt evidence is incomplete';
  END IF;

  INSERT INTO public.tasks (task_id, user_id, title, status)
  VALUES (
    '77777777-7777-4777-8777-777777777777',
    '11111111-1111-4111-8111-111111111111',
    'Synthetic failure',
    'pending'
  );
  INSERT INTO public.reminders (
    reminder_id, task_id, user_id, scheduled_time, status,
    intended_local_date, intended_local_time, intended_timezone, evidence_class
  ) VALUES (
    failure_reminder,
    '77777777-7777-4777-8777-777777777777',
    '11111111-1111-4111-8111-111111111111',
    now() - interval '30 seconds',
    'pending',
    current_date,
    localtime,
    'UTC',
    'production_synthetic'
  );
  failure_claim := public.claim_reminder_delivery(
    failure_reminder,
    '11111111-1111-4111-8111-111111111111',
    'delivery-failure-1'
  );
  failure_attempt := failure_claim #>> '{attempt,attempt_id}';
  PERFORM public.finish_reminder_delivery(
    failure_attempt,
    failure_reminder,
    '11111111-1111-4111-8111-111111111111',
    'error',
    'injected_provider_failure',
    'do_not_retry',
    NULL
  );
  IF NOT EXISTS (
    SELECT 1
    FROM public.reminder_delivery_attempts AS attempt
    JOIN public.reminder_occurrences AS occurrence USING (occurrence_id)
    WHERE occurrence.reminder_id = failure_reminder
      AND occurrence.terminal_at IS NOT NULL
      AND attempt.result = 'error'
      AND attempt.normalized_cause = 'injected_provider_failure'
  ) THEN
    RAISE EXCEPTION 'injected failure evidence is incomplete';
  END IF;

  PERFORM public.record_scheduler_heartbeat('beta-scheduler', 'sql-test', 1, 2, 3);
  health := public.get_reminder_reliability_health();
  IF NOT (health ->> 'scheduler_ready')::BOOLEAN
    OR (health ->> 'reconciliation_drift')::INT <> 6
    OR (health ->> 'staging_synthetic_occurrences')::INT <> 1
    OR (health ->> 'production_synthetic_occurrences')::INT <> 1
    OR jsonb_array_length(health -> 'reminder_lateness_ms') <> 1
    OR jsonb_array_length(health -> 'provider_latency_ms') <> 2
  THEN
    RAISE EXCEPTION 'reliability health is incomplete: %', health;
  END IF;

  BEGIN
    UPDATE public.reminder_occurrences
    SET confirmed_at = confirmed_at + interval '1 second'
    WHERE reminder_id = success_reminder;
    RAISE EXCEPTION 'occurrence history rewrite unexpectedly succeeded';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM = 'occurrence history rewrite unexpectedly succeeded' THEN
      RAISE;
    END IF;
  END;
  BEGIN
    DELETE FROM public.reminder_delivery_attempts WHERE attempt_id = failure_attempt;
    RAISE EXCEPTION 'attempt deletion unexpectedly succeeded';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM = 'attempt deletion unexpectedly succeeded' THEN
      RAISE;
    END IF;
  END;
  BEGIN
    UPDATE public.reminder_delivery_attempts
    SET normalized_cause = 'late_rewrite'
    WHERE attempt_id = success_attempt;
    RAISE EXCEPTION 'finished attempt rewrite unexpectedly succeeded';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM = 'finished attempt rewrite unexpectedly succeeded' THEN
      RAISE;
    END IF;
  END;
END;
$$;

SET ROLE authenticated;
DO $$
BEGIN
  BEGIN
    PERFORM public.get_reminder_reliability_health();
    RAISE EXCEPTION 'authenticated reliability function access unexpectedly succeeded';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
  BEGIN
    PERFORM 1 FROM public.reminder_delivery_attempts;
    RAISE EXCEPTION 'authenticated reliability table access unexpectedly succeeded';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
END;
$$;
RESET ROLE;
