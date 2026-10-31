\set ON_ERROR_STOP on
BEGIN;
DO $$ DECLARE
 fresh UUID := gen_random_uuid(); pending UUID := gen_random_uuid(); local_auth UUID := gen_random_uuid();
 u UUID; r JSONB;
BEGIN
 IF public.get_app_schema_version() <> 24 THEN RAISE EXCEPTION '024 not reported'; END IF;
 INSERT INTO public.pairing_tokens(token, supabase_auth_id, expires_at)
  VALUES ('t024-a', fresh, now() + interval '10 minutes'),
         ('t024-b', pending, now() + interval '10 minutes'),
         ('t024-c', pending, now() + interval '10 minutes'),
         ('t024-d', local_auth, now() + interval '10 minutes'),
         ('t024-e', fresh, now() + interval '10 minutes');

 -- No profile: another app never creates one, and the token survives.
 r := public.complete_pairing_v2('t024-a', 'fake2', 'ext-024a');
 IF r->>'status' <> 'account_required'
  OR EXISTS (SELECT 1 FROM public.user_profiles WHERE supabase_auth_id = fresh)
  OR (SELECT consumed FROM public.pairing_tokens WHERE token = 't024-a')
 THEN RAISE EXCEPTION '024 created or consumed for an unknown account'; END IF;

 -- A profile that has not finished Activation is refused too; once activated it links.
 INSERT INTO public.user_profiles(telegram_chat_id, supabase_auth_id)
  VALUES (91024001, pending) RETURNING user_id INTO u;
 IF public.complete_pairing_v2('t024-b', 'fake2', 'ext-024b')->>'status' <> 'account_required'
 THEN RAISE EXCEPTION '024 linked an unactivated account'; END IF;
 UPDATE public.user_profiles SET onboarding_complete = TRUE WHERE user_id = u;
 -- Call first: a subquery in the same statement would not see the function's insert.
 r := public.complete_pairing_v2('t024-c', 'fake2', 'ext-024b');
 IF r->>'status' <> 'paired'
  OR NOT EXISTS (SELECT 1 FROM public.channel_identities
    WHERE user_id = u AND channel = 'fake2' AND external_id = 'ext-024b')
 THEN RAISE EXCEPTION '024 refused an activated account'; END IF;

 -- The local CLI is still a first app; Telegram still creates through 015.
 r := public.complete_pairing_v2('t024-d', 'cli', 'dev-024');
 IF r->>'status' <> 'paired'
  OR (SELECT primary_channel FROM public.user_profiles WHERE supabase_auth_id = local_auth) <> 'cli'
 THEN RAISE EXCEPTION '024 broke the cli first app'; END IF;
 IF public.complete_pairing_v2('t024-e', 'telegram', '91024002')->>'status' <> 'paired'
 THEN RAISE EXCEPTION '024 broke Telegram first-app Pairing'; END IF;
END $$;
ROLLBACK;
