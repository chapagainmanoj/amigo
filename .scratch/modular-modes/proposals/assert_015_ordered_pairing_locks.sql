-- Reconstruction assertions; fixture effects roll back. No real participant data is used.
BEGIN;
DO $$
DECLARE
  v_auth UUID := '00000000-0000-0000-0000-000000015001';
  v_other UUID := '00000000-0000-0000-0000-000000015002';
  v_token TEXT := '00000000000000000000000000015001';
  v_again TEXT := '00000000000000000000000000015002';
  v_conflict TEXT := '00000000000000000000000000015003';
  v_invalid TEXT := '00000000000000000000000000015004';
  v_result JSONB;
  v_definition TEXT;
  v_config TEXT[];
  v_security BOOLEAN;
BEGIN
  IF public.get_app_schema_version() <> 15 THEN RAISE EXCEPTION '015 ledger not recorded'; END IF;
  -- Owner-only synthetic tokens isolate complete_pairing from Activation's issuance gate.
  INSERT INTO public.pairing_tokens(token, supabase_auth_id, expires_at)
    VALUES (v_token, v_auth, now() + interval '5 minutes');
  v_result := public.complete_pairing(v_token, 91015001);
  IF v_result->>'status' <> 'paired' OR NOT EXISTS (
    SELECT 1 FROM public.user_profiles WHERE telegram_chat_id = 91015001 AND supabase_auth_id = v_auth)
  THEN RAISE EXCEPTION 'happy-path identity not paired'; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.pairing_tokens
      WHERE token = v_token AND consumed AND consumed_at IS NOT NULL)
  THEN RAISE EXCEPTION 'pairing did not consume token'; END IF;
  IF public.complete_pairing(v_token, 91015001)->>'status' <> 'invalid_token'
  THEN RAISE EXCEPTION 'consumed token replay accepted'; END IF;
  INSERT INTO public.pairing_tokens(token, supabase_auth_id, expires_at)
    VALUES (v_again, v_auth, now() + interval '5 minutes');
  IF public.complete_pairing(v_again, 91015001)->>'status' <> 'already_paired'
  THEN RAISE EXCEPTION 'idempotent re-pair failed'; END IF;
  INSERT INTO public.user_profiles(telegram_chat_id, supabase_auth_id) VALUES (91015002, v_other);
  INSERT INTO public.pairing_tokens(token, supabase_auth_id, expires_at)
    VALUES (v_conflict, v_auth, now() + interval '5 minutes');
  IF public.complete_pairing(v_conflict, 91015002)->>'status' <> 'conflict'
     OR public.complete_pairing(v_conflict, 91015003)->>'status' <> 'conflict'
  THEN RAISE EXCEPTION 'identity conflict arm failed'; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.user_profiles WHERE telegram_chat_id = 91015002 AND supabase_auth_id = v_other)
     OR (SELECT consumed FROM public.pairing_tokens WHERE token = v_conflict)
  THEN RAISE EXCEPTION 'conflict changed identity or consumed token'; END IF;
  INSERT INTO public.pairing_tokens(token, supabase_auth_id, expires_at)
    VALUES (v_invalid, v_other, now() + interval '5 minutes');
  UPDATE public.pairing_tokens SET invalidated_at = now() WHERE token = v_invalid;
  IF public.complete_pairing(v_invalid, 91015002)->>'status' <> 'invalid_token'
  THEN RAISE EXCEPTION 'invalidated token accepted'; END IF;
  UPDATE public.pairing_tokens SET invalidated_at = NULL, expires_at = now() - interval '1 minute'
    WHERE token = v_invalid;
  IF public.complete_pairing(v_invalid, 91015002)->>'status' <> 'invalid_token'
     OR public.complete_pairing('unknown', 91015002)->>'status' <> 'invalid_token'
  THEN RAISE EXCEPTION 'expired/unknown token accepted'; END IF;

  SELECT lower(regexp_replace(regexp_replace(pg_get_functiondef(proc.oid), '--[^\n]*', '', 'g'),
           '\s+', ' ', 'g')), proc.proconfig, proc.prosecdef
    INTO v_definition, v_config, v_security
    FROM pg_catalog.pg_proc AS proc WHERE proc.oid = 'public.complete_pairing(text,bigint)'::regprocedure;
  IF v_definition !~ 'order by user_id loop perform 1 from public.user_profiles'
     OR v_definition !~ 'where user_id = v_candidate_user_id for update'
     OR v_definition !~ 'where telegram_chat_id = p_telegram_chat_id for update'
     OR v_definition !~ 'where supabase_auth_id = v_token.supabase_auth_id for update'
     OR NOT v_security OR NOT ('search_path=""' = ANY(v_config))
  THEN RAISE EXCEPTION 'ordered locks/locked re-reads/security boundary missing'; END IF;
  IF has_function_privilege('anon', 'public.complete_pairing(text,bigint)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.complete_pairing(text,bigint)', 'EXECUTE')
     OR NOT has_function_privilege('service_role', 'public.complete_pairing(text,bigint)', 'EXECUTE')
  THEN RAISE EXCEPTION 'pairing RPC role boundary broken'; END IF;
END;
$$;
ROLLBACK;
