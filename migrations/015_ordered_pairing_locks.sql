-- Reconstructed proposal, 2026-10-03. These are new bytes, not the missing original artifact.
-- No approval or adoption is implied. Business decisions match migration 003 exactly.
BEGIN;
DO $$
BEGIN
  IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 14) <> 14
     OR (SELECT max(version) FROM public.schema_migrations) <> 14 THEN
    RAISE EXCEPTION '015 requires the complete approved 001-014 chain';
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.complete_pairing(p_token TEXT, p_telegram_chat_id BIGINT)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_now TIMESTAMPTZ := now();
  v_token public.pairing_tokens%ROWTYPE;
  v_chat_user public.user_profiles%ROWTYPE;
  v_auth_user public.user_profiles%ROWTYPE;
  v_chat_exists BOOLEAN;
  v_auth_exists BOOLEAN;
  v_candidate_user_id UUID;
BEGIN
  SELECT * INTO v_token FROM public.pairing_tokens WHERE token = p_token FOR UPDATE;
  IF NOT FOUND OR v_token.consumed OR v_token.invalidated_at IS NOT NULL
     OR v_token.expires_at <= v_now THEN
    RETURN jsonb_build_object('status', 'invalid_token');
  END IF;

  -- Take both identity candidate locks in an explicit total order, one row per statement.
  FOR v_candidate_user_id IN
    SELECT user_id FROM public.user_profiles
    WHERE telegram_chat_id = p_telegram_chat_id OR supabase_auth_id = v_token.supabase_auth_id
    ORDER BY user_id
  LOOP
    PERFORM 1 FROM public.user_profiles WHERE user_id = v_candidate_user_id FOR UPDATE;
  END LOOP;

  -- Retain the original locked re-reads: a row can enter the predicate after the candidate
  -- snapshot. EvalPlanQual must protect that row before conflict decisions or identity writes.
  SELECT * INTO v_chat_user FROM public.user_profiles
    WHERE telegram_chat_id = p_telegram_chat_id FOR UPDATE;
  v_chat_exists := FOUND;
  SELECT * INTO v_auth_user FROM public.user_profiles
    WHERE supabase_auth_id = v_token.supabase_auth_id FOR UPDATE;
  v_auth_exists := FOUND;

  IF v_chat_exists AND v_auth_exists AND v_chat_user.user_id = v_auth_user.user_id THEN
    UPDATE public.pairing_tokens SET consumed = TRUE, consumed_at = v_now WHERE token = p_token;
    RETURN jsonb_build_object('status', 'already_paired');
  END IF;
  IF (v_chat_exists AND v_chat_user.supabase_auth_id IS NOT NULL
      AND v_chat_user.supabase_auth_id <> v_token.supabase_auth_id)
     OR (v_auth_exists AND v_auth_user.telegram_chat_id <> p_telegram_chat_id) THEN
    RETURN jsonb_build_object('status', 'conflict');
  END IF;
  IF v_chat_exists THEN
    UPDATE public.user_profiles SET supabase_auth_id = v_token.supabase_auth_id, updated_at = v_now
      WHERE user_id = v_chat_user.user_id RETURNING * INTO v_chat_user;
  ELSE
    INSERT INTO public.user_profiles(telegram_chat_id, supabase_auth_id)
      VALUES (p_telegram_chat_id, v_token.supabase_auth_id) RETURNING * INTO v_chat_user;
  END IF;
  UPDATE public.pairing_tokens SET consumed = TRUE, consumed_at = v_now WHERE token = p_token;
  RETURN jsonb_build_object('status', 'paired');
EXCEPTION WHEN unique_violation THEN
  RETURN jsonb_build_object('status', 'conflict');
END;
$$;

REVOKE ALL ON FUNCTION public.complete_pairing(TEXT, BIGINT) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.complete_pairing(TEXT, BIGINT) TO service_role;

-- Unlike the lost proposal's blind ledger insertion, verify the distinctive executable shape.
-- The independent behavioral concurrency probe is still required; this is not that proof.
DO $$
DECLARE v_definition TEXT;
BEGIN
  SELECT lower(regexp_replace(regexp_replace(
    pg_get_functiondef('public.complete_pairing(text,bigint)'::regprocedure),
    '--[^\n]*', '', 'g'), '\s+', ' ', 'g')) INTO v_definition;
  IF v_definition !~ 'order by user_id loop perform 1 from public.user_profiles'
     OR v_definition !~ 'where user_id = v_candidate_user_id for update'
     OR v_definition !~ 'where telegram_chat_id = p_telegram_chat_id for update'
     OR v_definition !~ 'where supabase_auth_id = v_token.supabase_auth_id for update' THEN
    RAISE EXCEPTION '015 ordered locks and locked re-reads not installed';
  END IF;
  INSERT INTO public.schema_migrations(version) VALUES (15);
END;
$$;
COMMIT;
