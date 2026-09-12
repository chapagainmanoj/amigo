# Review: Dashboard-First Activation Migration 013

Status: approved
Reviewer: independent agents (implementation and review performed by different agents)
Prepared: 2026-09-12

## Purpose

Issue 15 requires the dashboard-first Activation Journey: a verified Dashboard Account
acknowledges the beta limits, pairs Telegram, completes a profile and quiet hours, schedules one
private test Reminder, and resolves it. The application code for all of this is already staged —
`src/activation.py`, `src/memory/activation.py`, `src/api/activation.py`, and the
`ActivationJourney` dashboard view — and `MemoryStore` already calls four RPCs that exist in no
migration: `acknowledge_activation_terms`, `update_activation_profile`,
`create_activation_test_command`, and `get_activation_state`. `MemoryStore.create_pairing_token`
also already expects `issue_pairing_token` to raise `activation_not_acknowledged`, which
migration 003's version cannot do.

This migration adds the `activation_journeys` table, those four service-only functions, and
replaces `issue_pairing_token` to add the acknowledgement gate.

## Reconstruction note

The previously reviewed proposal bytes were lost when the OS cleaned `/tmp` between sessions. This
is a fresh reconstruction from the current application code, fakes, and tests. Its hashes differ
from the historical ones; this is not an exact reproduction and is not claimed to be.

- proposal `013_dashboard_first_activation.sql`:
  `b3a6ec8d7430d8899fa9202c77f77ceb2fb0e6c2d9814d5c10f20a21f3f8b2c7`
- assertions `activation_journey.sql`:
  `b62a22f3291e2971fb35c2c2463478bdf8532a43819e1aeda4813f2d20365942`
- lock-order guard `check_activation_lock_order.py`:
  `6ec34d71f2d9c3fa9ecad218cecfc60b48c87deeb981caadd85624b1eefcd8c5`
- historical proposal hash (not reproduced):
  `e081f2165e02ae50570c718ef3c77a73a26cd25ee8799c4bb2d2ab24e8d8534b`
- historical assertions hash (not reproduced):
  `057d055e3c447861786784dc38bda6643b46192cb957b33ec07ae5d91d0ac4d8`

## How this one was verified differently

`get_activation_state` has to reproduce the 341-line derivation in `src/memory/activation.py` and
`src/activation.py` in SQL. Hand-checking that is not credible, so a differential harness builds
the same scenario in a real PostgreSQL 15 database and in the in-memory mirror and diffs the two
read models field by field: **16/16 scenarios match**, covering every journey step, all four
pairing-token states, every delivery state, and all three resolutions.

The harness paid for itself by catching three defects before review: timestamps rendered in the
session timezone instead of UTC (fixed by pinning `SET timezone = 'UTC'` on all four functions),
a name-normalization divergence, and — via PostgreSQL's own ambiguity check — a
`WHERE reminder_id = reminder_id` in the assertions that would have matched every row.

## What the independent review changed

The first independent review returned CHANGES REQUIRED and found a blocking defect that neither
the assertions nor the differential harness could see, because it is a concurrency property:

**`create_activation_test_command` inverted the lock order.** It took a `user_profiles` row lock
before the identity's advisory lock, while `get_activation_state` took the advisory lock first.
A participant submitting the test Reminder while the dashboard polls `GET /api/activation`
deadlocks, and neither `MemoryStore` call site retries, so it surfaces as a 500.

The fix makes the identity's advisory lock unconditionally the **first** lock any Activation
function takes — before the receipt advisory lock and before any row lock. Measured with the
reviewer's own harness, unmodified:

| ordering | deadlocks per 300 concurrent calls |
|----------|-----------------------------------|
| as originally proposed | 88 (the reviewer independently measured 93) |
| as proposed here | 0 |

`scripts/check_activation_lock_order.py` is included so CI guards this. It is not a vacuous
check: it passes clean on this proposal and fails at 88 deadlocks when the original ordering is
restored.

The review also produced three further corrections:

- The database was acting as a third, subtly different name normalizer (tabs, non-breaking
  spaces, control characters, and the length gate all diverged from `validate_preferred_name`).
  It now validates and stores verbatim, matching `InMemoryStore` and `FakeStore`, leaving
  `src/api/activation.py` as the single normalizer.
- A genuine crash in `src/activation.py`: `tasks.deferred_count` is nullable, and
  `task.get("deferred_count", 0)` returns `None` for a present-but-NULL column, so `None > 0`
  raised `TypeError`. Fixed at both call sites with a regression test.
- Five mutants had survived the assertion file. Assertions were added for the pairing rate limit,
  `idempotency_key_conflict`, the cross-tenant Task guard, the `HH:MM` quiet-hours format,
  provider acceptance as delivery evidence, lateness, and resolution requiring Reminder
  acknowledgement. The kill rate went from 5/11 to 8/11.

## Deliberately untested, stated plainly

Three mutants still survive the assertion file, each for a reason rather than an oversight:

- `journey.updated_at` advancing cannot be observed from a single-transaction assertion file,
  because `now()` is transaction-scoped and every command inside one `DO` block shares an
  instant. The assertions instead prove the command stamps the journey's audit fields together.
- Removing the read model's row locks is a defensible alternative design, not a defect; the
  advisory lock is the real mutex.
- Re-inverting the lock order is a concurrency property no single-transaction SQL file can
  observe. `scripts/check_activation_lock_order.py` is what guards it.

## Adoption changes that must land in the same change

- `.github/workflows/ci.yml`: append `-f migrations/013_dashboard_first_activation.sql` then
  `-f tests/sql/activation_journey.sql` to the end of the existing psql chain, and add a step
  running `python scripts/check_activation_lock_order.py` against the built database.
- `README.md`: add step 15 and a sentence in the numeric-order paragraph.
- `tests/sql/activation_journey.sql` and `scripts/check_activation_lock_order.py` move in
  alongside the migration.
- The preflight warning block and the `013–014` references in `README.md`,
  `docs/what-is-amigo.md`, `docs/capability-matrix.md`, and `docs/pre-launch-gap-analysis.md`
  narrow to `014`.

## Proposed migration

```sql
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

  SELECT profile.*
  INTO profile_row
  FROM public.user_profiles AS profile
  WHERE profile.user_id = p_user_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'user_not_found';
  END IF;

  SELECT journey.*
  INTO journey_row
  FROM public.activation_journeys AS journey
  WHERE journey.auth_id = profile_row.supabase_auth_id
  FOR UPDATE;

  IF NOT FOUND OR journey_row.profile_completed_at IS NULL THEN
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
```

## Proposed assertions (tests/sql/activation_journey.sql)

```sql
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

  -- `now()` is transaction-scoped, so an assertion file running in one transaction cannot
  -- observe updated_at advancing between commands. What it can prove is that the command
  -- stamps the journey's audit fields together from one instant.
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

RESET ROLE;
SET ROLE anon;

DO $$
BEGIN
  IF has_table_privilege(current_user, 'public.activation_journeys', 'SELECT')
    OR has_function_privilege(current_user, 'public.get_activation_state(uuid)', 'EXECUTE')
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
  THEN
    RAISE EXCEPTION 'Authenticated role retained Activation access';
  END IF;
END;
$$;

RESET ROLE;
```

## Proposed lock-order guard (scripts/check_activation_lock_order.py)

```python
"""Fail if the Activation functions can deadlock against each other.

Migration 013's functions take an auth-id advisory lock and a `user_profiles` row
lock. If any of them takes the row lock first, a participant submitting the test
Reminder deadlocks against the dashboard polling `GET /api/activation`, and neither
call site retries. This drives that exact interleave.

Connection comes from the standard libpq environment (PGHOST, PGPORT, PGUSER,
PGDATABASE, PGPASSWORD), so it needs no arguments in CI.

Usage: python scripts/check_activation_lock_order.py [--trials N]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

CONCURRENT_READERS = 4


def _psql(statement: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["psql", "-t", "-A", "-c", statement],
        capture_output=True,
        text=True,
    )


def _trial() -> list[str]:
    auth, user = str(uuid.uuid4()), str(uuid.uuid4())
    chat = uuid.uuid4().int % 10**12
    _psql(f"SELECT public.acknowledge_activation_terms('{auth}','2026-08-29');")
    _psql(
        "INSERT INTO public.user_profiles(user_id, telegram_chat_id, supabase_auth_id)"
        f" VALUES ('{user}',{chat},'{auth}');",
    )
    _psql(
        f"SELECT public.update_activation_profile('{auth}','Probe','America/Toronto',"
        "'07:00','22:30');",
    )

    scheduled = datetime.now(UTC) + timedelta(minutes=2)
    local = scheduled.astimezone(ZoneInfo("America/Toronto"))
    create = (
        f"SELECT public.create_activation_test_command('{user}','k-{uuid.uuid4().hex}',"
        f"'{'a' * 64}','probe',false,'{scheduled.isoformat()}','{local.date()}',"
        f"'{local.time().replace(microsecond=0)}','America/Toronto');"
    )

    results: dict[str, subprocess.CompletedProcess] = {}

    def run(name: str, statement: str) -> None:
        results[name] = _psql(statement)

    threads = [threading.Thread(target=run, args=("create", create))]
    threads += [
        threading.Thread(
            target=run, args=(f"read{index}", f"SELECT public.get_activation_state('{auth}');")
        )
        for index in range(CONCURRENT_READERS)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    return [
        f"{name}: {result.stderr.splitlines()[0]}"
        for name, result in results.items()
        if "deadlock" in result.stderr
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=30)
    args = parser.parse_args()

    deadlocks: list[str] = []
    for _ in range(args.trials):
        deadlocks.extend(_trial())

    calls = args.trials * (CONCURRENT_READERS + 1)
    if deadlocks:
        print(f"FAIL: {len(deadlocks)} deadlocks in {args.trials} trials ({calls} calls)")
        for line in deadlocks[:5]:
            print(f"  {line}")
        print("The Activation functions must take the auth-id advisory lock before the")
        print("user_profiles row lock. See migration 013.")
        return 1

    print(f"ok: no deadlocks in {args.trials} trials ({calls} concurrent calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## Review checklist

- [x] The four RPCs match the parameter names and result shapes `MemoryStore` already calls.
- [x] The read model matches the Python mirror on 16 differential scenarios.
- [x] Acknowledgement is immutable and idempotent; a superseding policy version fails closed.
- [x] Pairing is gated on an acknowledged journey, and the replacement preserves 003's rate limit.
- [x] The profile locks once the test is scheduled; repeating it does not advance the journey.
- [x] The test command is idempotent by receipt and refuses a second non-retry test.
- [x] Retry is allowed only for failed, missed, cancelled, or overdue-pending Reminders.
- [x] The occurrence row is left to migration 011's trigger, never double-inserted.
- [x] Completion is finalized only from durable delivery AND resolution evidence.
- [x] Activation state never leaks across participants.
- [x] Every Activation function takes the identity advisory lock before any other lock.
- [x] Anonymous and authenticated roles lose the table and all four functions.

## Decision

Approved by the project owner on 2026-09-12 in response to the request
`approve migration 013`. Added in the same change as:

- `migrations/013_dashboard_first_activation.sql`
  (`b3a6ec8d7430d8899fa9202c77f77ceb2fb0e6c2d9814d5c10f20a21f3f8b2c7`)
- `tests/sql/activation_journey.sql`
  (`b62a22f3291e2971fb35c2c2463478bdf8532a43819e1aeda4813f2d20365942`)
- `scripts/check_activation_lock_order.py`
  (`6ec34d71f2d9c3fa9ecad218cecfc60b48c87deeb981caadd85624b1eefcd8c5`)
- the `.github/workflows/ci.yml` chain extension and the new deadlock-guard step
- `README.md` step 15, its numeric-order description, and the narrowed preflight warning
- the `014` corrections to `README.md`, `docs/what-is-amigo.md`, `docs/capability-matrix.md`,
  and `docs/pre-launch-gap-analysis.md`, which previously said `013–014`

Post-adoption verification: the chain parsed verbatim out of `.github/workflows/ci.yml` applied
clean to a fresh PostgreSQL 15.12 database; the lock-order guard reported no deadlocks in 200
concurrent calls against that database; 258 backend tests, Ruff, `git diff --check`, and the
dashboard lint/build all pass.

Timing note: the project owner approved while a second independent re-review of the revised bytes
was still running. The first independent review's blocking finding was fixed and re-measured
before approval was requested. Any finding the re-review returns will be recorded here and acted
on rather than deferred.
