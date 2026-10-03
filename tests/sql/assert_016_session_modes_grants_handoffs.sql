-- PROPOSAL assertions. Run on an isolated chain after 016; rollback all fixture state.
BEGIN;

DO $$
DECLARE
  v_users UUID[] := ARRAY[]::UUID[];
  v_user UUID;
  v_session UUID;
  v_other_session UUID;
  v_handoff UUID;
  v_result JSONB;
  v_count INT;
  v_i INT;
BEGIN
  IF public.get_app_schema_version() <> 16 THEN RAISE EXCEPTION '016 not reported'; END IF;
  FOR v_i IN 1..6 LOOP
    INSERT INTO public.user_profiles(telegram_chat_id, supabase_auth_id)
      VALUES (91016000 + v_i, ('00000000-0000-0000-0000-' || lpad(v_i::TEXT, 12, '0'))::UUID)
      RETURNING user_id INTO v_user;
    v_users := array_append(v_users, v_user);
  END LOOP;
  INSERT INTO public.sessions(user_id) VALUES (v_users[1]) RETURNING session_id INTO v_session;
  INSERT INTO public.sessions(user_id) VALUES (v_users[2]) RETURNING session_id INTO v_other_session;
  IF (SELECT active_mode_id FROM public.sessions WHERE session_id = v_session) IS NOT NULL THEN
    RAISE EXCEPTION 'existing/new Session default changed';
  END IF;

  -- Refusal before any cleanup/grant/audit side effect; the separate concurrency probe
  -- also blocks this owned profile and lets a valid short expiry elapse during the wait.
  IF public.grant_mode('ffffffff-ffff-ffff-ffff-ffffffffffff'::UUID,
      'reflect', 'operator-a', 'Missing owner')->>'status' <> 'invalid'
  THEN RAISE EXCEPTION 'missing grant owner was accepted'; END IF;
  IF public.grant_mode(v_users[1], 'reflect', 'operator-a', 'Already expired',
      clock_timestamp() - interval '1 second')->>'status' <> 'invalid'
  THEN RAISE EXCEPTION 'past grant expiry was accepted'; END IF;
  IF EXISTS (SELECT 1 FROM public.mode_grants WHERE mode_id = 'reflect')
     OR EXISTS (SELECT 1 FROM public.mode_grant_events WHERE mode_id = 'reflect')
  THEN RAISE EXCEPTION 'invalid grant created a row or audit event'; END IF;

  FOR v_i IN 1..5 LOOP
    v_result := public.grant_mode(v_users[v_i], 'coach', 'operator-a', 'Opt-in trial');
    IF v_result->>'status' <> 'granted' THEN RAISE EXCEPTION 'grant failed: %', v_result; END IF;
  END LOOP;
  IF public.grant_mode(v_users[6], 'coach', 'operator-a', 'Sixth participant')->>'status' <> 'cap_reached'
  THEN RAISE EXCEPTION 'sixth active grant was accepted'; END IF;
  IF public.grant_mode(v_users[1], 'coach', 'operator-b', 'Duplicate')->>'status' <> 'already_active'
  THEN RAISE EXCEPTION 'duplicate grant was not idempotent'; END IF;
  IF public.grant_mode(v_users[6], 'reflect', 'operator-a', '', now() + interval '1 day')->>'status' <> 'invalid'
  THEN RAISE EXCEPTION 'empty reason accepted'; END IF;
  IF public.grant_mode(v_users[6], 'reflect', 'operator-a', 'Too long', now() + interval '15 days')->>'status' <> 'invalid'
  THEN RAISE EXCEPTION 'trial longer than 14 days accepted'; END IF;
  IF public.revoke_mode_grant(v_users[5], 'coach', 'operator-b', 'Trial ended')->>'status' <> 'revoked'
  THEN RAISE EXCEPTION 'revoke failed'; END IF;
  IF public.grant_mode(v_users[6], 'coach', 'operator-a', 'Replace revoked')->>'status' <> 'granted'
  THEN RAISE EXCEPTION 'revocation did not free capacity'; END IF;
  IF (SELECT count(*) FROM public.mode_grant_events WHERE mode_id = 'coach' AND action = 'granted') <> 6
     OR (SELECT count(*) FROM public.mode_grant_events WHERE mode_id = 'coach' AND action = 'revoked') <> 1
  THEN RAISE EXCEPTION 'grant audit incomplete'; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.mode_grant_events
    WHERE user_id = v_users[5] AND action = 'revoked' AND operator = 'operator-b' AND reason = 'Trial ended')
  THEN RAISE EXCEPTION 'operator/reason audit lost'; END IF;

  -- Owner-only fixture expires a grant; application credentials cannot perform this mutation.
  UPDATE public.mode_grants SET granted_at = now() - interval '15 days',
    expires_at = now() - interval '1 day' WHERE user_id = v_users[6] AND mode_id = 'coach';
  IF public.grant_mode(v_users[6], 'coach', 'operator-c', 'Renew expired')->>'status' <> 'granted'
  THEN RAISE EXCEPTION 'expired grant prevented renewal'; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.mode_grant_events
    WHERE user_id = v_users[6] AND action = 'expired' AND operator = 'operator-c')
  THEN RAISE EXCEPTION 'expiration not audited'; END IF;
  BEGIN
    INSERT INTO public.mode_grants(user_id, mode_id, expires_at, granted_by, reason)
      VALUES (v_users[1], 'coach', now() + interval '1 day', 'owner-fixture', 'Duplicate');
    RAISE EXCEPTION 'one-open-grant uniqueness missing';
  EXCEPTION WHEN unique_violation THEN NULL; END;

  IF public.set_active_mode(v_users[2], v_session, 'coach')->>'status' <> 'unavailable'
  THEN RAISE EXCEPTION 'cross-tenant Session was updated'; END IF;
  IF public.set_active_mode(v_users[1], v_session, 'coach')->>'status' <> 'set'
  THEN RAISE EXCEPTION 'Mode entry failed'; END IF;
  v_result := public.create_mode_handoff(v_users[1], v_session, 'coach', 'daily', 'Add buy milk');
  IF v_result->>'status' <> 'pending' THEN RAISE EXCEPTION 'proposal failed: %', v_result; END IF;
  v_handoff := (v_result->'handoff'->>'handoff_id')::UUID;
  IF public.resolve_mode_handoff(v_users[2], v_session, v_handoff, TRUE)->>'status' <> 'unavailable'
  THEN RAISE EXCEPTION 'cross-tenant confirmation accepted'; END IF;
  IF (SELECT resolved_at FROM public.mode_handoffs WHERE handoff_id = v_handoff) IS NOT NULL
  THEN RAISE EXCEPTION 'cross-tenant tap consumed handoff'; END IF;
  v_result := public.resolve_mode_handoff(v_users[1], v_session, v_handoff, TRUE);
  IF v_result->>'status' <> 'confirmed' OR v_result->'handoff'->>'carried_request' <> 'Add buy milk'
     OR v_result->'handoff'->>'resolution' <> 'confirmed'
     OR v_result->'handoff'->>'resolved_at' IS NULL
  THEN RAISE EXCEPTION 'confirmation lost approved request'; END IF;
  IF (SELECT active_mode_id FROM public.sessions WHERE session_id = v_session) IS NOT NULL
  THEN RAISE EXCEPTION 'confirmation did not atomically enter Daily'; END IF;
  IF public.resolve_mode_handoff(v_users[1], v_session, v_handoff, TRUE)->>'status' <> 'unavailable'
  THEN RAISE EXCEPTION 'handoff replay accepted'; END IF;

  PERFORM public.set_active_mode(v_users[1], v_session, 'coach');
  v_result := public.create_mode_handoff(v_users[1], v_session, 'coach', 'daily', 'Decline this');
  v_handoff := (v_result->'handoff'->>'handoff_id')::UUID;
  IF public.resolve_mode_handoff(v_users[1], v_session, v_handoff, FALSE)->>'status' <> 'declined'
     OR (SELECT active_mode_id FROM public.sessions WHERE session_id = v_session) <> 'coach'
  THEN RAISE EXCEPTION 'decline changed active Mode'; END IF;
  v_result := public.create_mode_handoff(v_users[1], v_session, 'coach', 'daily', 'Too late');
  v_handoff := (v_result->'handoff'->>'handoff_id')::UUID;
  UPDATE public.mode_handoffs SET created_at = now() - interval '20 minutes',
    expires_at = now() - interval '10 minutes' WHERE handoff_id = v_handoff;
  IF public.resolve_mode_handoff(v_users[1], v_session, v_handoff, TRUE)->>'status' <> 'expired'
     OR (SELECT active_mode_id FROM public.sessions WHERE session_id = v_session) <> 'coach'
  THEN RAISE EXCEPTION 'expired handoff entered target Mode'; END IF;
  v_result := public.create_mode_handoff(v_users[1], v_session, 'coach', 'daily', 'Revoke before tap');
  v_handoff := (v_result->'handoff'->>'handoff_id')::UUID;
  PERFORM public.revoke_mode_grant(v_users[1], 'coach', 'operator-b', 'Stop trial');
  IF public.resolve_mode_handoff(v_users[1], v_session, v_handoff, TRUE)->>'status' <> 'unavailable'
  THEN RAISE EXCEPTION 'revoked grant allowed handoff'; END IF;
  BEGIN
    INSERT INTO public.mode_handoffs(user_id, session_id, source_mode_id, target_mode_id,
                                    source_grant_required, target_grant_required, carried_request, expires_at)
      VALUES (v_users[1], v_other_session, 'coach', 'daily', TRUE, FALSE,
              'Wrong owner', now() + interval '1 minute');
    RAISE EXCEPTION 'composite Session ownership foreign key missing';
  EXCEPTION WHEN foreign_key_violation THEN NULL; END;

  IF public.set_active_mode(v_users[1], v_session, 'coach')->>'status' <> 'unavailable'
  THEN RAISE EXCEPTION 'revoked/ungranted specialized Mode entry accepted'; END IF;
  IF public.set_active_mode(v_users[1], v_session, 'journal', FALSE)->>'status' <> 'set'
  THEN RAISE EXCEPTION 'activated non-Daily Mode incorrectly requires grant'; END IF;
  v_result := public.create_mode_handoff(
    v_users[1], v_session, 'journal', 'reflect', 'Activated-only handoff', FALSE, FALSE);
  IF v_result->>'status' <> 'pending' THEN RAISE EXCEPTION 'activated-mode handoff refused'; END IF;
  v_handoff := (v_result->'handoff'->>'handoff_id')::UUID;
  v_result := public.resolve_mode_handoff(v_users[1], v_session, v_handoff, TRUE);
  IF v_result->>'status' <> 'confirmed'
     OR (SELECT active_mode_id FROM public.sessions WHERE session_id = v_session) <> 'reflect'
  THEN RAISE EXCEPTION 'activated-mode confirmation incorrectly requires grant: %, active=%',
    v_result, (SELECT active_mode_id FROM public.sessions WHERE session_id = v_session); END IF;

  -- Read isolation proven with real authenticated role + JWT identity in separate blocks below.
  PERFORM set_config('amigo.test_user', v_users[1]::TEXT, TRUE);
  PERFORM set_config('amigo.other_user', v_users[2]::TEXT, TRUE);
END;
$$;

SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claim.sub', '00000000-0000-0000-0000-000000000001', TRUE);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.mode_grants) THEN RAISE EXCEPTION 'own grants invisible'; END IF;
  IF EXISTS (SELECT 1 FROM public.mode_grants WHERE user_id <> current_setting('amigo.test_user')::UUID)
     OR EXISTS (SELECT 1 FROM public.mode_grant_events WHERE user_id <> current_setting('amigo.test_user')::UUID)
     OR EXISTS (SELECT 1 FROM public.mode_handoffs WHERE user_id <> current_setting('amigo.test_user')::UUID)
  THEN RAISE EXCEPTION 'tenant read isolation failed'; END IF;
  IF has_table_privilege('authenticated', 'public.mode_grants', 'INSERT,UPDATE,DELETE')
     OR has_function_privilege('authenticated', 'public.grant_mode(uuid,text,text,text,timestamptz)', 'EXECUTE')
     OR has_function_privilege('authenticated', 'public.resolve_mode_handoff(uuid,uuid,uuid,boolean)', 'EXECUTE')
  THEN RAISE EXCEPTION 'authenticated role can mutate Mode authority'; END IF;
END;
$$;
RESET ROLE;
DO $$
DECLARE v_name TEXT;
BEGIN
  FOREACH v_name IN ARRAY ARRAY['mode_grants', 'mode_grant_events', 'mode_handoffs'] LOOP
    IF has_table_privilege('anon', 'public.' || v_name, 'SELECT,INSERT,UPDATE,DELETE')
       OR has_table_privilege('service_role', 'public.' || v_name, 'INSERT,UPDATE,DELETE')
    THEN RAISE EXCEPTION 'direct Mode authority DML retained: %', v_name; END IF;
  END LOOP;
  IF has_function_privilege('anon', 'public.create_mode_handoff(uuid,uuid,text,text,text,boolean,boolean)', 'EXECUTE')
  THEN RAISE EXCEPTION 'anonymous handoff creation allowed'; END IF;
END;
$$;
ROLLBACK;
