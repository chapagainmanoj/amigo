BEGIN;

ALTER TABLE public.pairing_tokens ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pairing_tokens
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN consumed SET NOT NULL,
  ADD COLUMN consumed_at TIMESTAMPTZ,
  ADD COLUMN invalidated_at TIMESTAMPTZ;

REVOKE ALL ON TABLE public.pairing_tokens FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.pairing_tokens TO service_role;

DROP INDEX IF EXISTS public.idx_pairing_tokens_expiry;

CREATE INDEX idx_pairing_tokens_active_expiry
  ON public.pairing_tokens(expires_at)
  WHERE consumed = FALSE AND invalidated_at IS NULL;

CREATE INDEX idx_pairing_tokens_auth_created
  ON public.pairing_tokens(supabase_auth_id, created_at DESC);

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

CREATE OR REPLACE FUNCTION public.complete_pairing(
  p_token TEXT,
  p_telegram_chat_id BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  v_now TIMESTAMPTZ := now();
  v_token public.pairing_tokens%ROWTYPE;
  v_chat_user public.user_profiles%ROWTYPE;
  v_auth_user public.user_profiles%ROWTYPE;
  v_chat_exists BOOLEAN;
  v_auth_exists BOOLEAN;
BEGIN
  SELECT *
  INTO v_token
  FROM public.pairing_tokens
  WHERE token = p_token
  FOR UPDATE;

  IF NOT FOUND
    OR v_token.consumed
    OR v_token.invalidated_at IS NOT NULL
    OR v_token.expires_at <= v_now
  THEN
    RETURN jsonb_build_object('status', 'invalid_token');
  END IF;

  SELECT *
  INTO v_chat_user
  FROM public.user_profiles
  WHERE telegram_chat_id = p_telegram_chat_id
  FOR UPDATE;
  v_chat_exists := FOUND;

  SELECT *
  INTO v_auth_user
  FROM public.user_profiles
  WHERE supabase_auth_id = v_token.supabase_auth_id
  FOR UPDATE;
  v_auth_exists := FOUND;

  IF v_chat_exists
    AND v_auth_exists
    AND v_chat_user.user_id = v_auth_user.user_id
  THEN
    UPDATE public.pairing_tokens
    SET consumed = TRUE, consumed_at = v_now
    WHERE token = p_token;

    RETURN jsonb_build_object('status', 'already_paired');
  END IF;

  IF (v_chat_exists
      AND v_chat_user.supabase_auth_id IS NOT NULL
      AND v_chat_user.supabase_auth_id <> v_token.supabase_auth_id)
    OR (v_auth_exists AND v_auth_user.telegram_chat_id <> p_telegram_chat_id)
  THEN
    RETURN jsonb_build_object('status', 'conflict');
  END IF;

  IF v_chat_exists THEN
    UPDATE public.user_profiles
    SET supabase_auth_id = v_token.supabase_auth_id,
        updated_at = v_now
    WHERE user_id = v_chat_user.user_id
    RETURNING * INTO v_chat_user;
  ELSE
    INSERT INTO public.user_profiles(telegram_chat_id, supabase_auth_id)
    VALUES (p_telegram_chat_id, v_token.supabase_auth_id)
    RETURNING * INTO v_chat_user;
  END IF;

  UPDATE public.pairing_tokens
  SET consumed = TRUE, consumed_at = v_now
  WHERE token = p_token;

  RETURN jsonb_build_object('status', 'paired');
EXCEPTION
  WHEN unique_violation THEN
    RETURN jsonb_build_object('status', 'conflict');
END;
$$;

REVOKE ALL ON FUNCTION public.issue_pairing_token(TEXT, UUID, TIMESTAMPTZ)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_pairing(TEXT, BIGINT)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.issue_pairing_token(TEXT, UUID, TIMESTAMPTZ)
  TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_pairing(TEXT, BIGINT)
  TO service_role;

COMMENT ON FUNCTION public.issue_pairing_token(TEXT, UUID, TIMESTAMPTZ)
  IS 'Service-role-only atomic Pairing-token issuance, invalidation, and rate limiting.';
COMMENT ON FUNCTION public.complete_pairing(TEXT, BIGINT)
  IS 'Service-role-only atomic Pairing-token consumption and identity linking.';

COMMIT;
