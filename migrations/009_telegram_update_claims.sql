BEGIN;

CREATE TABLE public.telegram_update_claims (
  update_id BIGINT PRIMARY KEY CHECK (update_id >= 0),
  telegram_chat_id BIGINT NOT NULL,
  update_kind TEXT NOT NULL CHECK (
    update_kind IN ('message', 'callback_query')
  ),
  status TEXT NOT NULL DEFAULT 'processing' CHECK (
    status IN ('processing', 'completed', 'failed')
  ),
  failure_code TEXT CHECK (
    failure_code IS NULL OR length(failure_code) BETWEEN 1 AND 100
  ),
  claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  CHECK (
    (status = 'processing' AND finished_at IS NULL AND failure_code IS NULL)
    OR (status = 'completed' AND finished_at IS NOT NULL AND failure_code IS NULL)
    OR (status = 'failed' AND finished_at IS NOT NULL AND failure_code IS NOT NULL)
  )
);

CREATE INDEX idx_telegram_update_claims_claimed_at
  ON public.telegram_update_claims(claimed_at);

CREATE INDEX idx_telegram_update_claims_unfinished
  ON public.telegram_update_claims(claimed_at)
  WHERE status = 'processing';

ALTER TABLE public.telegram_update_claims ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.telegram_update_claims FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE public.telegram_update_claims TO service_role;

CREATE OR REPLACE FUNCTION public.claim_telegram_update(
  p_update_id BIGINT,
  p_telegram_chat_id BIGINT,
  p_update_kind TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  claimed_update public.telegram_update_claims%ROWTYPE;
BEGIN
  IF p_update_id IS NULL OR p_update_id < 0 THEN
    RAISE EXCEPTION 'invalid_telegram_update_id';
  END IF;
  IF p_telegram_chat_id IS NULL THEN
    RAISE EXCEPTION 'invalid_telegram_chat_id';
  END IF;
  IF p_update_kind IS NULL OR p_update_kind NOT IN ('message', 'callback_query') THEN
    RAISE EXCEPTION 'invalid_telegram_update_kind';
  END IF;

  INSERT INTO public.telegram_update_claims (
    update_id,
    telegram_chat_id,
    update_kind
  )
  VALUES (
    p_update_id,
    p_telegram_chat_id,
    p_update_kind
  )
  ON CONFLICT (update_id) DO NOTHING
  RETURNING * INTO claimed_update;

  IF FOUND THEN
    RETURN jsonb_build_object(
      'claimed', true,
      'update_id', claimed_update.update_id,
      'telegram_chat_id', claimed_update.telegram_chat_id,
      'update_kind', claimed_update.update_kind,
      'status', claimed_update.status,
      'failure_code', claimed_update.failure_code,
      'claimed_at', claimed_update.claimed_at,
      'finished_at', claimed_update.finished_at
    );
  END IF;

  SELECT claim.*
  INTO claimed_update
  FROM public.telegram_update_claims AS claim
  WHERE claim.update_id = p_update_id;

  IF claimed_update.telegram_chat_id <> p_telegram_chat_id
    OR claimed_update.update_kind <> p_update_kind
  THEN
    RAISE EXCEPTION 'telegram_update_identity_conflict';
  END IF;

  RETURN jsonb_build_object(
    'claimed', false,
    'update_id', claimed_update.update_id,
    'telegram_chat_id', claimed_update.telegram_chat_id,
    'update_kind', claimed_update.update_kind,
    'status', claimed_update.status,
    'failure_code', claimed_update.failure_code,
    'claimed_at', claimed_update.claimed_at,
    'finished_at', claimed_update.finished_at
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.finish_telegram_update(
  p_update_id BIGINT,
  p_status TEXT,
  p_failure_code TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  finished_update public.telegram_update_claims%ROWTYPE;
BEGIN
  IF p_update_id IS NULL OR p_update_id < 0 THEN
    RAISE EXCEPTION 'invalid_telegram_update_id';
  END IF;
  IF p_status IS NULL OR p_status NOT IN ('completed', 'failed') THEN
    RAISE EXCEPTION 'invalid_telegram_update_status';
  END IF;
  IF (p_status = 'completed' AND p_failure_code IS NOT NULL)
    OR (p_status = 'failed' AND (
      p_failure_code IS NULL OR length(p_failure_code) NOT BETWEEN 1 AND 100
    ))
  THEN
    RAISE EXCEPTION 'invalid_telegram_failure_code';
  END IF;

  UPDATE public.telegram_update_claims AS claim
  SET status = p_status,
      failure_code = p_failure_code,
      finished_at = now()
  WHERE claim.update_id = p_update_id
    AND claim.status = 'processing'
  RETURNING * INTO finished_update;

  IF NOT FOUND THEN
    SELECT claim.*
    INTO finished_update
    FROM public.telegram_update_claims AS claim
    WHERE claim.update_id = p_update_id;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'telegram_update_not_found';
    END IF;
    IF finished_update.status <> p_status
      OR finished_update.failure_code IS DISTINCT FROM p_failure_code
    THEN
      RAISE EXCEPTION 'telegram_update_already_finished';
    END IF;
  END IF;

  RETURN jsonb_build_object(
    'update_id', finished_update.update_id,
    'telegram_chat_id', finished_update.telegram_chat_id,
    'update_kind', finished_update.update_kind,
    'status', finished_update.status,
    'failure_code', finished_update.failure_code,
    'claimed_at', finished_update.claimed_at,
    'finished_at', finished_update.finished_at
  );
END;
$$;

REVOKE ALL ON FUNCTION public.claim_telegram_update(BIGINT, BIGINT, TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_telegram_update(BIGINT, BIGINT, TEXT)
  TO service_role;

REVOKE ALL ON FUNCTION public.finish_telegram_update(BIGINT, TEXT, TEXT)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.finish_telegram_update(BIGINT, TEXT, TEXT)
  TO service_role;

COMMIT;
