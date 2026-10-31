-- ADR 0006: second-app Pairing never creates an account, enforced in the database.
-- complete_pairing_v2 is copied from 022 with one added rule: for channels other than telegram
-- (which delegates to 015 before this point) and cli (local development only), the token's
-- dashboard account must already have an activated profile; otherwise 'account_required'.
BEGIN;
DO $$ BEGIN
 IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 23) <> 23
 OR (SELECT max(version) FROM public.schema_migrations) <> 23 THEN
 RAISE EXCEPTION '024 requires the complete approved 001-023 chain'; END IF;
END $$;

CREATE OR REPLACE FUNCTION public.complete_pairing_v2(p_token TEXT, p_channel TEXT, p_external_id TEXT)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_now TIMESTAMPTZ := now();
  v_token public.pairing_tokens%ROWTYPE;
  v_auth_user public.user_profiles%ROWTYPE;
  v_auth_exists BOOLEAN;
  v_owner_id UUID;
  v_candidate_user_id UUID;
BEGIN
  IF p_channel IS NULL OR p_channel !~ '^[a-z][a-z0-9_]{1,31}$'
     OR p_external_id IS NULL OR length(p_external_id) NOT BETWEEN 1 AND 200
     OR p_external_id <> btrim(p_external_id) THEN
    RAISE EXCEPTION 'invalid_channel_identity';
  END IF;
  IF p_channel = 'telegram' THEN
    IF p_external_id !~ '^-?[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'invalid_channel_identity'; END IF;
    RETURN public.complete_pairing(p_token, p_external_id::BIGINT);
  END IF;

  SELECT * INTO v_token FROM public.pairing_tokens WHERE token = p_token FOR UPDATE;
  IF NOT FOUND OR v_token.consumed OR v_token.invalidated_at IS NOT NULL
     OR v_token.expires_at <= v_now THEN
    RETURN jsonb_build_object('status', 'invalid_token');
  END IF;

  FOR v_candidate_user_id IN
    SELECT user_id FROM public.user_profiles
    WHERE supabase_auth_id = v_token.supabase_auth_id
       OR user_id IN (SELECT ci.user_id FROM public.channel_identities ci
                      WHERE ci.channel = p_channel AND ci.external_id = p_external_id)
    ORDER BY user_id
  LOOP
    PERFORM 1 FROM public.user_profiles WHERE user_id = v_candidate_user_id FOR UPDATE;
  END LOOP;

  SELECT ci.user_id INTO v_owner_id FROM public.channel_identities ci
    WHERE ci.channel = p_channel AND ci.external_id = p_external_id FOR UPDATE;
  SELECT * INTO v_auth_user FROM public.user_profiles
    WHERE supabase_auth_id = v_token.supabase_auth_id FOR UPDATE;
  v_auth_exists := FOUND;
  -- ADR 0006: apps other than Telegram (and the local cli) only join an existing, activated
  -- account; they never create one. The token stays unconsumed so the dashboard can explain.
  IF p_channel <> 'cli' AND (NOT v_auth_exists OR v_auth_user.onboarding_complete IS NOT TRUE) THEN
    RETURN jsonb_build_object('status', 'account_required');
  END IF;

  IF v_owner_id IS NOT NULL AND v_auth_exists AND v_owner_id = v_auth_user.user_id THEN
    UPDATE public.pairing_tokens SET consumed = TRUE, consumed_at = v_now WHERE token = p_token;
    RETURN jsonb_build_object('status', 'already_paired');
  END IF;
  IF v_owner_id IS NOT NULL
     OR (v_auth_exists AND EXISTS (SELECT 1 FROM public.channel_identities ci
         WHERE ci.user_id = v_auth_user.user_id AND ci.channel = p_channel)) THEN
    RETURN jsonb_build_object('status', 'conflict');
  END IF;
  IF v_auth_exists THEN
    UPDATE public.user_profiles SET updated_at = v_now WHERE user_id = v_auth_user.user_id;
  ELSE
    INSERT INTO public.user_profiles(supabase_auth_id, primary_channel)
      VALUES (v_token.supabase_auth_id, p_channel) RETURNING * INTO v_auth_user;
  END IF;
  INSERT INTO public.channel_identities(user_id, channel, external_id)
    VALUES (v_auth_user.user_id, p_channel, p_external_id);
  UPDATE public.pairing_tokens SET consumed = TRUE, consumed_at = v_now WHERE token = p_token;
  RETURN jsonb_build_object('status', 'paired');
EXCEPTION WHEN unique_violation THEN
  RETURN jsonb_build_object('status', 'conflict');
END;
$$;

DO $$ BEGIN
 IF to_regprocedure('public.complete_pairing_v2(text,text,text)') IS NULL
  OR position('account_required' IN pg_get_functiondef(
       'public.complete_pairing_v2(text,text,text)'::regprocedure)) = 0
 THEN RAISE EXCEPTION '024 complete_pairing_v2 was not replaced'; END IF;
 IF has_function_privilege('authenticated', 'public.complete_pairing_v2(text,text,text)', 'EXECUTE')
  OR has_function_privilege('anon', 'public.complete_pairing_v2(text,text,text)', 'EXECUTE')
  OR NOT has_function_privilege('service_role', 'public.complete_pairing_v2(text,text,text)', 'EXECUTE')
 THEN RAISE EXCEPTION '024 complete_pairing_v2 privileges wrong'; END IF;
 INSERT INTO public.schema_migrations(version) VALUES(24);
END $$;
COMMIT;
