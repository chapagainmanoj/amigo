BEGIN;

CREATE TYPE public.reminder_evidence_class AS ENUM (
  'participant',
  'staging_synthetic',
  'production_synthetic'
);

CREATE TYPE public.reminder_attempt_result AS ENUM (
  'accepted',
  'rejected',
  'timeout',
  'error'
);

CREATE TYPE public.reminder_retry_decision AS ENUM (
  'retry',
  'do_not_retry',
  'unknown'
);

ALTER TABLE public.reminders
  ADD COLUMN evidence_class public.reminder_evidence_class NOT NULL DEFAULT 'participant';

CREATE TABLE public.reminder_occurrences (
  occurrence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reminder_id UUID NOT NULL UNIQUE REFERENCES public.reminders(reminder_id),
  user_id UUID NOT NULL REFERENCES public.user_profiles(user_id),
  task_id UUID NOT NULL REFERENCES public.tasks(task_id),
  evidence_class public.reminder_evidence_class NOT NULL DEFAULT 'participant',
  measurable BOOLEAN NOT NULL DEFAULT true,
  unmeasurable_reason TEXT CHECK (
    unmeasurable_reason IS NULL OR length(unmeasurable_reason) BETWEEN 1 AND 100
  ),
  confirmed_at TIMESTAMPTZ,
  scheduled_for TIMESTAMPTZ NOT NULL,
  first_claimed_at TIMESTAMPTZ,
  provider_accepted_at TIMESTAMPTZ,
  terminal_at TIMESTAMPTZ,
  acknowledged_at TIMESTAMPTZ,
  cancelled_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (measurable OR unmeasurable_reason IS NOT NULL),
  CHECK (provider_accepted_at IS NULL OR first_claimed_at IS NOT NULL),
  CHECK (acknowledged_at IS NULL OR terminal_at IS NOT NULL),
  CHECK (cancelled_at IS NULL OR terminal_at IS NOT NULL)
);

CREATE INDEX idx_reminder_occurrences_scheduled
  ON public.reminder_occurrences(evidence_class, scheduled_for);

CREATE TABLE public.reminder_delivery_attempts (
  attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  occurrence_id UUID NOT NULL REFERENCES public.reminder_occurrences(occurrence_id),
  user_id UUID NOT NULL REFERENCES public.user_profiles(user_id),
  attempt_number INT NOT NULL CHECK (attempt_number > 0),
  idempotency_key TEXT NOT NULL UNIQUE CHECK (
    length(btrim(idempotency_key)) BETWEEN 1 AND 200
  ),
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  provider_accepted_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  result public.reminder_attempt_result,
  normalized_cause TEXT CHECK (
    normalized_cause IS NULL OR length(normalized_cause) BETWEEN 1 AND 100
  ),
  retry_decision public.reminder_retry_decision NOT NULL DEFAULT 'unknown',
  provider_latency_ms BIGINT CHECK (provider_latency_ms IS NULL OR provider_latency_ms >= 0),
  UNIQUE (occurrence_id, attempt_number),
  CHECK (
    (finished_at IS NULL AND result IS NULL)
    OR (finished_at IS NOT NULL AND result IS NOT NULL)
  ),
  CHECK (provider_accepted_at IS NULL OR result = 'accepted')
);

CREATE INDEX idx_reminder_delivery_attempts_started
  ON public.reminder_delivery_attempts(started_at);

CREATE TABLE public.scheduler_runtime (
  owner_key TEXT PRIMARY KEY CHECK (length(btrim(owner_key)) BETWEEN 1 AND 100),
  worker_id TEXT NOT NULL CHECK (length(btrim(worker_id)) BETWEEN 1 AND 100),
  heartbeat_at TIMESTAMPTZ NOT NULL,
  reconciled_at TIMESTAMPTZ,
  missing_jobs INT NOT NULL DEFAULT 0 CHECK (missing_jobs >= 0),
  wrong_time_jobs INT NOT NULL DEFAULT 0 CHECK (wrong_time_jobs >= 0),
  inverse_drift_jobs INT NOT NULL DEFAULT 0 CHECK (inverse_drift_jobs >= 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.reminder_occurrences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reminder_delivery_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.scheduler_runtime ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.reminder_occurrences FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.reminder_delivery_attempts FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.scheduler_runtime FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.reminder_occurrences TO service_role;
GRANT ALL ON TABLE public.reminder_delivery_attempts TO service_role;
GRANT ALL ON TABLE public.scheduler_runtime TO service_role;

INSERT INTO public.reminder_occurrences (
  reminder_id,
  user_id,
  task_id,
  evidence_class,
  measurable,
  unmeasurable_reason,
  confirmed_at,
  scheduled_for,
  first_claimed_at,
  provider_accepted_at,
  terminal_at,
  acknowledged_at,
  cancelled_at,
  created_at
)
SELECT
  reminder.reminder_id,
  reminder.user_id,
  reminder.task_id,
  reminder.evidence_class,
  false,
  'pre_instrumentation',
  NULL,
  reminder.scheduled_time,
  NULL,
  NULL,
  CASE WHEN reminder.status IN ('acknowledged', 'missed', 'failed', 'cancelled')
    THEN reminder.created_at ELSE NULL END,
  CASE WHEN reminder.status = 'acknowledged' THEN reminder.created_at ELSE NULL END,
  CASE WHEN reminder.status = 'cancelled' THEN reminder.created_at ELSE NULL END,
  reminder.created_at
FROM public.reminders AS reminder;

CREATE OR REPLACE FUNCTION public.capture_reminder_occurrence()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  event_time TIMESTAMPTZ := now();
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO public.reminder_occurrences (
      reminder_id, user_id, task_id, evidence_class,
      confirmed_at, scheduled_for, created_at
    ) VALUES (
      NEW.reminder_id,
      NEW.user_id,
      NEW.task_id,
      NEW.evidence_class,
      NEW.created_at,
      NEW.scheduled_time,
      NEW.created_at
    );
    RETURN NEW;
  END IF;

  UPDATE public.reminder_occurrences AS occurrence
  SET
    first_claimed_at = CASE
      WHEN NEW.status = 'sending' THEN COALESCE(occurrence.first_claimed_at, event_time)
      ELSE occurrence.first_claimed_at
    END,
    provider_accepted_at = CASE
      WHEN NEW.status = 'sent' THEN COALESCE(occurrence.provider_accepted_at, event_time)
      ELSE occurrence.provider_accepted_at
    END,
    terminal_at = CASE
      WHEN NEW.status IN ('acknowledged', 'missed', 'failed', 'cancelled')
        THEN COALESCE(occurrence.terminal_at, event_time)
      ELSE occurrence.terminal_at
    END,
    acknowledged_at = CASE
      WHEN NEW.status = 'acknowledged'
        THEN COALESCE(occurrence.acknowledged_at, event_time)
      ELSE occurrence.acknowledged_at
    END,
    cancelled_at = CASE
      WHEN NEW.status = 'cancelled'
        THEN COALESCE(occurrence.cancelled_at, event_time)
      ELSE occurrence.cancelled_at
    END
  WHERE occurrence.reminder_id = NEW.reminder_id;
  RETURN NEW;
END;
$$;

CREATE TRIGGER capture_reminder_occurrence_insert
AFTER INSERT ON public.reminders
FOR EACH ROW EXECUTE FUNCTION public.capture_reminder_occurrence();

CREATE TRIGGER capture_reminder_occurrence_status
AFTER UPDATE OF status ON public.reminders
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION public.capture_reminder_occurrence();

CREATE OR REPLACE FUNCTION public.prevent_reliability_history_rewrite()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'reliability_history_is_immutable';
  END IF;
  IF OLD.reminder_id <> NEW.reminder_id
    OR OLD.user_id <> NEW.user_id
    OR OLD.task_id <> NEW.task_id
    OR OLD.evidence_class <> NEW.evidence_class
    OR OLD.measurable <> NEW.measurable
    OR OLD.unmeasurable_reason IS DISTINCT FROM NEW.unmeasurable_reason
    OR OLD.confirmed_at IS DISTINCT FROM NEW.confirmed_at
    OR OLD.scheduled_for IS DISTINCT FROM NEW.scheduled_for
    OR (OLD.first_claimed_at IS NOT NULL AND OLD.first_claimed_at IS DISTINCT FROM NEW.first_claimed_at)
    OR (OLD.provider_accepted_at IS NOT NULL AND OLD.provider_accepted_at IS DISTINCT FROM NEW.provider_accepted_at)
    OR (OLD.terminal_at IS NOT NULL AND OLD.terminal_at IS DISTINCT FROM NEW.terminal_at)
    OR (OLD.acknowledged_at IS NOT NULL AND OLD.acknowledged_at IS DISTINCT FROM NEW.acknowledged_at)
    OR (OLD.cancelled_at IS NOT NULL AND OLD.cancelled_at IS DISTINCT FROM NEW.cancelled_at)
    OR OLD.created_at IS DISTINCT FROM NEW.created_at
  THEN
    RAISE EXCEPTION 'reliability_history_is_immutable';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER prevent_reminder_occurrence_rewrite
BEFORE UPDATE OR DELETE ON public.reminder_occurrences
FOR EACH ROW EXECUTE FUNCTION public.prevent_reliability_history_rewrite();

CREATE OR REPLACE FUNCTION public.prevent_attempt_rewrite()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'reliability_history_is_immutable';
  END IF;
  IF OLD.finished_at IS NOT NULL AND OLD IS DISTINCT FROM NEW THEN
    RAISE EXCEPTION 'reliability_history_is_immutable';
  END IF;
  IF OLD.occurrence_id <> NEW.occurrence_id
    OR OLD.user_id <> NEW.user_id
    OR OLD.attempt_number <> NEW.attempt_number
    OR OLD.idempotency_key <> NEW.idempotency_key
    OR OLD.started_at <> NEW.started_at
    OR (OLD.finished_at IS NOT NULL AND OLD.finished_at IS DISTINCT FROM NEW.finished_at)
    OR (OLD.result IS NOT NULL AND OLD.result IS DISTINCT FROM NEW.result)
    OR (OLD.provider_accepted_at IS NOT NULL AND OLD.provider_accepted_at IS DISTINCT FROM NEW.provider_accepted_at)
    OR (OLD.normalized_cause IS NOT NULL AND OLD.normalized_cause IS DISTINCT FROM NEW.normalized_cause)
    OR (OLD.retry_decision <> 'unknown' AND OLD.retry_decision IS DISTINCT FROM NEW.retry_decision)
    OR (OLD.provider_latency_ms IS NOT NULL AND OLD.provider_latency_ms IS DISTINCT FROM NEW.provider_latency_ms)
  THEN
    RAISE EXCEPTION 'reliability_history_is_immutable';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER prevent_reminder_attempt_rewrite
BEFORE UPDATE OR DELETE ON public.reminder_delivery_attempts
FOR EACH ROW EXECUTE FUNCTION public.prevent_attempt_rewrite();

CREATE OR REPLACE FUNCTION public.claim_reminder_delivery(
  p_reminder_id UUID,
  p_user_id UUID,
  p_idempotency_key TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  reminder_row public.reminders%ROWTYPE;
  occurrence_row public.reminder_occurrences%ROWTYPE;
  attempt_row public.reminder_delivery_attempts%ROWTYPE;
  task_state public.task_status;
BEGIN
  IF btrim(COALESCE(p_idempotency_key, '')) = ''
    OR length(p_idempotency_key) > 200
  THEN
    RAISE EXCEPTION 'invalid_delivery_idempotency_key';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_reminder_id::TEXT, 0));

  SELECT attempt.* INTO attempt_row
  FROM public.reminder_delivery_attempts AS attempt
  WHERE attempt.idempotency_key = p_idempotency_key;
  IF FOUND THEN
    IF attempt_row.user_id <> p_user_id OR NOT EXISTS (
      SELECT 1
      FROM public.reminder_occurrences AS occurrence
      WHERE occurrence.occurrence_id = attempt_row.occurrence_id
        AND occurrence.reminder_id = p_reminder_id
    ) THEN
      RAISE EXCEPTION 'delivery_idempotency_key_conflict';
    END IF;
    RETURN jsonb_build_object('claimed', false, 'attempt', to_jsonb(attempt_row));
  END IF;

  SELECT reminder.* INTO reminder_row
  FROM public.reminders AS reminder
  WHERE reminder.reminder_id = p_reminder_id
    AND reminder.user_id = p_user_id
    AND reminder.status = 'pending'
  FOR UPDATE;
  IF NOT FOUND THEN
    RETURN jsonb_build_object('claimed', false);
  END IF;

  SELECT task.status INTO task_state
  FROM public.tasks AS task
  WHERE task.task_id = reminder_row.task_id AND task.user_id = p_user_id;
  IF task_state IS NULL OR task_state <> 'pending' THEN
    RETURN jsonb_build_object('claimed', false);
  END IF;

  SELECT occurrence.* INTO occurrence_row
  FROM public.reminder_occurrences AS occurrence
  WHERE occurrence.reminder_id = p_reminder_id;

  INSERT INTO public.reminder_delivery_attempts (
    occurrence_id, user_id, attempt_number, idempotency_key
  ) VALUES (
    occurrence_row.occurrence_id,
    p_user_id,
    1 + (SELECT count(*) FROM public.reminder_delivery_attempts
      WHERE occurrence_id = occurrence_row.occurrence_id),
    p_idempotency_key
  ) RETURNING * INTO attempt_row;

  UPDATE public.reminders SET status = 'sending'
  WHERE reminder_id = p_reminder_id AND user_id = p_user_id;

  RETURN jsonb_build_object(
    'claimed', true,
    'reminder', to_jsonb(reminder_row),
    'task_status', task_state,
    'occurrence_id', occurrence_row.occurrence_id,
    'attempt', to_jsonb(attempt_row)
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.finish_reminder_delivery(
  p_attempt_id UUID,
  p_reminder_id UUID,
  p_user_id UUID,
  p_result public.reminder_attempt_result,
  p_normalized_cause TEXT,
  p_retry_decision public.reminder_retry_decision,
  p_telegram_message_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  attempt_row public.reminder_delivery_attempts%ROWTYPE;
  finished_time TIMESTAMPTZ := now();
BEGIN
  IF p_result IS NULL OR p_retry_decision IS NULL THEN
    RAISE EXCEPTION 'invalid_delivery_outcome';
  END IF;
  IF p_retry_decision = 'unknown'
    OR (p_result = 'accepted' AND p_retry_decision <> 'do_not_retry')
    OR (
      p_result <> 'accepted'
      AND btrim(COALESCE(p_normalized_cause, '')) = ''
    )
  THEN
    RAISE EXCEPTION 'invalid_delivery_outcome';
  END IF;
  IF p_result = 'accepted' AND p_telegram_message_id IS NULL THEN
    RAISE EXCEPTION 'accepted_delivery_requires_message_id';
  END IF;

  UPDATE public.reminder_delivery_attempts AS attempt
  SET
    finished_at = finished_time,
    provider_accepted_at = CASE WHEN p_result = 'accepted' THEN finished_time ELSE NULL END,
    result = p_result,
    normalized_cause = CASE
      WHEN p_normalized_cause IS NULL THEN NULL ELSE left(p_normalized_cause, 100)
    END,
    retry_decision = p_retry_decision,
    provider_latency_ms = GREATEST(
      0,
      round(extract(epoch FROM (finished_time - attempt.started_at)) * 1000)::BIGINT
    )
  WHERE attempt.attempt_id = p_attempt_id
    AND attempt.user_id = p_user_id
    AND attempt.finished_at IS NULL
    AND EXISTS (
      SELECT 1
      FROM public.reminder_occurrences AS occurrence
      WHERE occurrence.occurrence_id = attempt.occurrence_id
        AND occurrence.reminder_id = p_reminder_id
        AND occurrence.user_id = p_user_id
    )
  RETURNING * INTO attempt_row;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'delivery_attempt_not_found_or_finished';
  END IF;

  UPDATE public.reminders AS reminder
  SET
    status = CASE
      WHEN p_result = 'accepted' THEN 'sent'::public.reminder_status
      WHEN p_retry_decision = 'retry' THEN 'pending'::public.reminder_status
      ELSE 'failed'::public.reminder_status
    END,
    telegram_message_id = CASE
      WHEN p_result = 'accepted' THEN p_telegram_message_id
      ELSE reminder.telegram_message_id
    END
  WHERE reminder.reminder_id = p_reminder_id
    AND reminder.user_id = p_user_id
    AND reminder.status = 'sending';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'reminder_delivery_state_conflict';
  END IF;

  RETURN jsonb_build_object('attempt', to_jsonb(attempt_row));
END;
$$;

CREATE OR REPLACE FUNCTION public.record_scheduler_heartbeat(
  p_owner_key TEXT,
  p_worker_id TEXT,
  p_missing_jobs INT,
  p_wrong_time_jobs INT,
  p_inverse_drift_jobs INT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF btrim(COALESCE(p_owner_key, '')) = '' OR btrim(COALESCE(p_worker_id, '')) = ''
    OR p_missing_jobs < 0 OR p_wrong_time_jobs < 0 OR p_inverse_drift_jobs < 0
  THEN
    RAISE EXCEPTION 'invalid_scheduler_heartbeat';
  END IF;
  INSERT INTO public.scheduler_runtime (
    owner_key, worker_id, heartbeat_at, reconciled_at,
    missing_jobs, wrong_time_jobs, inverse_drift_jobs, updated_at
  ) VALUES (
    p_owner_key, p_worker_id, now(), now(),
    p_missing_jobs, p_wrong_time_jobs, p_inverse_drift_jobs, now()
  )
  ON CONFLICT (owner_key) DO UPDATE SET
    worker_id = EXCLUDED.worker_id,
    heartbeat_at = EXCLUDED.heartbeat_at,
    reconciled_at = EXCLUDED.reconciled_at,
    missing_jobs = EXCLUDED.missing_jobs,
    wrong_time_jobs = EXCLUDED.wrong_time_jobs,
    inverse_drift_jobs = EXCLUDED.inverse_drift_jobs,
    updated_at = EXCLUDED.updated_at;
END;
$$;

CREATE OR REPLACE FUNCTION public.get_reminder_reliability_health()
RETURNS JSONB
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
SELECT jsonb_build_object(
  'database_checked_at', statement_timestamp(),
  'scheduler_heartbeat_at', runtime.heartbeat_at,
  'scheduler_ready', COALESCE(runtime.heartbeat_at >= statement_timestamp() - interval '2 minutes', false),
  'reconciliation_drift', COALESCE(runtime.missing_jobs + runtime.wrong_time_jobs + runtime.inverse_drift_jobs, 0),
  'outbox_pending', (SELECT count(*) FROM public.scheduler_outbox WHERE status = 'pending'),
  'outbox_oldest_pending_at', (SELECT min(created_at) FROM public.scheduler_outbox WHERE status = 'pending'),
  'outbox_oldest_pending_age_ms', COALESCE((SELECT GREATEST(
    0,
    round(extract(epoch FROM (statement_timestamp() - min(created_at))) * 1000)::BIGINT
  ) FROM public.scheduler_outbox WHERE status = 'pending'), 0),
  'outbox_failed', (SELECT count(*) FROM public.scheduler_outbox WHERE status = 'failed'),
  'eligible_occurrences', (SELECT count(*) FROM public.reminder_occurrences WHERE measurable),
  'accepted_occurrences', (SELECT count(*) FROM public.reminder_occurrences WHERE measurable AND provider_accepted_at IS NOT NULL),
  'reminder_lateness_ms', COALESCE((SELECT jsonb_agg(
    GREATEST(0, round(extract(epoch FROM (provider_accepted_at - scheduled_for)) * 1000)::BIGINT)
  ) FROM public.reminder_occurrences WHERE measurable AND provider_accepted_at IS NOT NULL), '[]'::JSONB),
  'scheduler_lag_ms', COALESCE((SELECT jsonb_agg(
    GREATEST(0, round(extract(epoch FROM (first_claimed_at - scheduled_for)) * 1000)::BIGINT)
  ) FROM public.reminder_occurrences WHERE measurable AND first_claimed_at IS NOT NULL), '[]'::JSONB),
  'provider_latency_ms', COALESCE((SELECT jsonb_agg(provider_latency_ms)
    FROM public.reminder_delivery_attempts WHERE provider_latency_ms IS NOT NULL), '[]'::JSONB),
  'attempt_failures', (SELECT count(*) FROM public.reminder_delivery_attempts
    WHERE result IN ('rejected', 'timeout', 'error')),
  'participant_occurrences', (SELECT count(*) FROM public.reminder_occurrences
    WHERE evidence_class = 'participant'),
  'staging_synthetic_occurrences', (SELECT count(*) FROM public.reminder_occurrences
    WHERE evidence_class = 'staging_synthetic'),
  'production_synthetic_occurrences', (SELECT count(*) FROM public.reminder_occurrences
    WHERE evidence_class = 'production_synthetic')
)
FROM (SELECT * FROM public.scheduler_runtime WHERE owner_key = 'beta-scheduler') AS runtime
RIGHT JOIN (SELECT 1) AS singleton ON true;
$$;

REVOKE ALL ON FUNCTION public.capture_reminder_occurrence() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_reminder_delivery(UUID, UUID, TEXT)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.finish_reminder_delivery(
  UUID, UUID, UUID, public.reminder_attempt_result, TEXT,
  public.reminder_retry_decision, BIGINT
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.record_scheduler_heartbeat(TEXT, TEXT, INT, INT, INT)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.get_reminder_reliability_health()
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.claim_reminder_delivery(UUID, UUID, TEXT)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.finish_reminder_delivery(
  UUID, UUID, UUID, public.reminder_attempt_result, TEXT,
  public.reminder_retry_decision, BIGINT
) TO service_role;
GRANT EXECUTE ON FUNCTION public.record_scheduler_heartbeat(TEXT, TEXT, INT, INT, INT)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.get_reminder_reliability_health()
  TO service_role;

COMMIT;
