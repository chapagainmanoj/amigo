BEGIN;

ALTER TYPE public.task_status RENAME TO task_status_legacy;

CREATE TYPE public.task_status AS ENUM (
  'pending',
  'completed',
  'skipped',
  'cancelled'
);

ALTER TABLE public.tasks
  ALTER COLUMN status DROP DEFAULT;

ALTER TABLE public.tasks
  ALTER COLUMN status TYPE public.task_status
  USING (
    CASE status::text
      WHEN 'done' THEN 'completed'
      WHEN 'deferred' THEN 'pending'
      ELSE status::text
    END
  )::public.task_status;

ALTER TABLE public.tasks
  ALTER COLUMN status SET DEFAULT 'pending'::public.task_status,
  ADD COLUMN version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0);

DROP TYPE public.task_status_legacy;

DROP INDEX IF EXISTS public.idx_tasks_user_date;
CREATE INDEX idx_tasks_user_due_status
  ON public.tasks(user_id, due_date, status);

CREATE TABLE public.command_receipts (
  receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.user_profiles(user_id),
  idempotency_key TEXT NOT NULL CHECK (
    length(btrim(idempotency_key)) BETWEEN 1 AND 200
  ),
  command_type TEXT NOT NULL,
  payload_hash TEXT NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
  result JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, idempotency_key)
);

CREATE INDEX idx_command_receipts_created_at
  ON public.command_receipts(created_at);

ALTER TABLE public.command_receipts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.command_receipts FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.command_receipts TO service_role;

REVOKE INSERT ON TABLE public.tasks FROM authenticated;
DROP POLICY IF EXISTS task_insert_own ON public.tasks;

CREATE OR REPLACE FUNCTION public.create_task_command(
  p_user_id UUID,
  p_idempotency_key TEXT,
  p_payload_hash TEXT,
  p_title TEXT,
  p_category public.task_category,
  p_due_date DATE,
  p_source_session_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  existing_receipt public.command_receipts%ROWTYPE;
  created_task public.tasks%ROWTYPE;
  command_result JSONB;
BEGIN
  IF p_user_id IS NULL OR NOT EXISTS (
    SELECT 1
    FROM public.user_profiles AS profile
    WHERE profile.user_id = p_user_id
  ) THEN
    RAISE EXCEPTION 'user_not_found';
  END IF;

  IF p_idempotency_key IS NULL
    OR length(btrim(p_idempotency_key)) NOT BETWEEN 1 AND 200
  THEN
    RAISE EXCEPTION 'invalid_idempotency_key';
  END IF;

  IF p_payload_hash IS NULL OR p_payload_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid_payload_hash';
  END IF;

  IF p_title IS NULL OR length(btrim(p_title)) NOT BETWEEN 1 AND 500 THEN
    RAISE EXCEPTION 'invalid_task_title';
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

  IF p_source_session_id IS NOT NULL AND NOT EXISTS (
    SELECT 1
    FROM public.sessions AS session
    WHERE session.session_id = p_source_session_id
      AND session.user_id = p_user_id
  ) THEN
    RAISE EXCEPTION 'session_not_found';
  END IF;

  INSERT INTO public.tasks (
    user_id,
    title,
    category,
    due_date,
    status,
    source_session_id,
    created_date,
    version
  )
  VALUES (
    p_user_id,
    btrim(p_title),
    p_category,
    p_due_date,
    'pending',
    p_source_session_id,
    CURRENT_DATE,
    1
  )
  RETURNING * INTO created_task;

  command_result := jsonb_build_object('task', to_jsonb(created_task));

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
    'create_task',
    p_payload_hash,
    command_result
  );

  RETURN command_result;
END;
$$;

REVOKE ALL ON FUNCTION public.create_task_command(
  UUID,
  TEXT,
  TEXT,
  TEXT,
  public.task_category,
  DATE,
  UUID
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.create_task_command(
  UUID,
  TEXT,
  TEXT,
  TEXT,
  public.task_category,
  DATE,
  UUID
) TO service_role;

COMMIT;
