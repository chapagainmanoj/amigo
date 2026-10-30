\set ON_ERROR_STOP on
BEGIN;
DO $$ DECLARE
 legacy UUID; tg UUID; owner_auth UUID := gen_random_uuid(); other_auth UUID := gen_random_uuid();
 owner UUID; r JSONB; task UUID; reminder UUID; attempt UUID;
BEGIN
 IF public.get_app_schema_version() <> 22 THEN RAISE EXCEPTION '022 not reported'; END IF;

 -- Legacy writers mirror into channel_identities and default to Telegram as primary.
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES (91022001) RETURNING user_id INTO tg;
 IF NOT EXISTS (SELECT 1 FROM public.channel_identities
   WHERE user_id = tg AND channel = 'telegram' AND external_id = '91022001')
  OR (SELECT primary_channel FROM public.user_profiles WHERE user_id = tg) <> 'telegram'
 THEN RAISE EXCEPTION 'Telegram identity not mirrored on insert'; END IF;
 UPDATE public.user_profiles SET telegram_chat_id = 91022002 WHERE user_id = tg;
 IF (SELECT external_id FROM public.channel_identities WHERE user_id = tg AND channel = 'telegram')
   <> '91022002' THEN RAISE EXCEPTION 'Telegram identity not mirrored on update'; END IF;

 -- First app is not Telegram: the token creates the profile with that app as primary.
 INSERT INTO public.pairing_tokens(token, supabase_auth_id, expires_at)
  VALUES ('t022-a', owner_auth, now() + interval '10 minutes'),
         ('t022-b', owner_auth, now() + interval '10 minutes'),
         ('t022-c', owner_auth, now() + interval '10 minutes'),
         ('t022-d', other_auth, now() + interval '10 minutes'),
         ('t022-e', owner_auth, now() + interval '10 minutes'),
         ('t022-f', owner_auth, now() + interval '10 minutes');
 IF public.complete_pairing_v2('t022-a', 'fake2', 'ext-1')->>'status' <> 'paired'
 THEN RAISE EXCEPTION 'first non-Telegram Pairing failed'; END IF;
 SELECT user_id INTO owner FROM public.user_profiles WHERE supabase_auth_id = owner_auth;
 IF (SELECT primary_channel FROM public.user_profiles WHERE user_id = owner) <> 'fake2'
  OR (SELECT telegram_chat_id FROM public.user_profiles WHERE user_id = owner) IS NOT NULL
 THEN RAISE EXCEPTION 'non-Telegram profile shape wrong'; END IF;
 IF public.complete_pairing_v2('t022-a', 'fake2', 'ext-1')->>'status' <> 'invalid_token'
 THEN RAISE EXCEPTION 'consumed token reused'; END IF;
 IF public.complete_pairing_v2('t022-b', 'fake2', 'ext-1')->>'status' <> 'already_paired'
 THEN RAISE EXCEPTION 'same identity not idempotent'; END IF;

 -- Second app on the same signed-in account links to the existing profile (015:54 NULL case).
 IF public.complete_pairing_v2('t022-c', 'telegram', '91022003')->>'status' <> 'paired'
 THEN RAISE EXCEPTION 'Telegram as second app did not link'; END IF;
 IF (SELECT count(*) FROM public.user_profiles WHERE supabase_auth_id = owner_auth) <> 1
  OR (SELECT telegram_chat_id FROM public.user_profiles WHERE user_id = owner) <> 91022003
  OR NOT EXISTS (SELECT 1 FROM public.channel_identities
    WHERE user_id = owner AND channel = 'telegram' AND external_id = '91022003')
 THEN RAISE EXCEPTION 'second app created a profile or missed the identity'; END IF;

 -- Conflicts: someone else's identity; a different id on an already linked channel;
 -- an unlinked legacy Telegram profile plus an existing signed-in profile.
 IF public.complete_pairing_v2('t022-d', 'fake2', 'ext-1')->>'status' <> 'conflict'
 THEN RAISE EXCEPTION 'foreign identity taken'; END IF;
 IF public.complete_pairing_v2('t022-e', 'fake2', 'ext-2')->>'status' <> 'conflict'
 THEN RAISE EXCEPTION 'second id on one channel accepted'; END IF;
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES (91022004) RETURNING user_id INTO legacy;
 UPDATE public.user_profiles SET telegram_chat_id = NULL WHERE user_id = owner;
 IF public.complete_pairing('t022-f', 91022004)->>'status' <> 'conflict'
 THEN RAISE EXCEPTION 'two profiles merged silently'; END IF;
 UPDATE public.user_profiles SET telegram_chat_id = 91022003 WHERE user_id = owner;
 BEGIN
  PERFORM public.complete_pairing_v2('t022-f', 'telegram', 'abc');
  RAISE EXCEPTION 'non-numeric Telegram id accepted';
 EXCEPTION WHEN raise_exception THEN
  IF SQLERRM <> 'invalid_channel_identity' THEN RAISE; END IF;
 END;
END $$;

-- Primary channel must be linked; the deferred key also guards direct writes and unlinking.
DO $$ DECLARE u UUID; BEGIN
 SELECT user_id INTO u FROM public.channel_identities WHERE channel = 'fake2' AND external_id = 'ext-1';
 IF public.set_primary_channel(u, 'telegram') <> 'telegram' THEN RAISE EXCEPTION 'switch failed'; END IF;
 BEGIN
  PERFORM public.set_primary_channel(u, 'slack');
  RAISE EXCEPTION 'unlinked primary accepted';
 EXCEPTION WHEN raise_exception THEN
  IF SQLERRM <> 'channel_not_linked' THEN RAISE; END IF;
 END;
 BEGIN
  UPDATE public.user_profiles SET primary_channel = 'slack' WHERE user_id = u;
  SET CONSTRAINTS ALL IMMEDIATE;
  RAISE EXCEPTION 'direct unlinked primary accepted';
 EXCEPTION WHEN foreign_key_violation THEN NULL;
 END;
 SET CONSTRAINTS ALL DEFERRED;
END $$;

-- Update claims: per-channel keys; Telegram keeps its table and is reshaped to text ids.
DO $$ DECLARE r JSONB; BEGIN
 r := public.claim_channel_update('fake2', 'u-1', 'ext-1', 'message');
 IF NOT (r->>'claimed')::BOOLEAN OR r->>'channel' <> 'fake2' THEN RAISE EXCEPTION 'claim failed'; END IF;
 IF (public.claim_channel_update('fake2', 'u-1', 'ext-1', 'message')->>'claimed')::BOOLEAN
 THEN RAISE EXCEPTION 'double claim'; END IF;
 IF NOT (public.claim_channel_update('fake3', 'u-1', 'ext-1', 'message')->>'claimed')::BOOLEAN
 THEN RAISE EXCEPTION 'update ids are not per channel'; END IF;
 BEGIN
  PERFORM public.claim_channel_update('fake2', 'u-1', 'ext-9', 'message');
  RAISE EXCEPTION 'identity conflict accepted';
 EXCEPTION WHEN raise_exception THEN
  IF SQLERRM <> 'channel_update_identity_conflict' THEN RAISE; END IF;
 END;
 r := public.finish_channel_update('fake2', 'u-1', 'completed');
 IF r->>'status' <> 'completed' OR r ? 'claimed' THEN RAISE EXCEPTION 'finish shape wrong'; END IF;
 r := public.claim_channel_update('telegram', '9022001', '91022003', 'message');
 IF NOT (r->>'claimed')::BOOLEAN OR r->>'update_id' <> '9022001' OR r->>'external_id' <> '91022003'
  OR r ? 'telegram_chat_id'
  OR NOT EXISTS (SELECT 1 FROM public.telegram_update_claims WHERE update_id = 9022001)
 THEN RAISE EXCEPTION 'Telegram claim not delegated: %', r; END IF;
 IF public.finish_channel_update('telegram', '9022001', 'completed')->>'status' <> 'completed'
 THEN RAISE EXCEPTION 'Telegram finish not delegated'; END IF;
END $$;

-- Delivery proof: a channel-neutral ref; Telegram also keeps telegram_message_id.
DO $$ DECLARE u UUID; task UUID := gen_random_uuid(); rem UUID := gen_random_uuid();
 claim JSONB; BEGIN
 SELECT user_id INTO u FROM public.channel_identities WHERE channel = 'fake2' AND external_id = 'ext-1';
 INSERT INTO public.tasks(task_id, user_id, title, status) VALUES (task, u, 'Synthetic 022', 'pending');
 INSERT INTO public.reminders(reminder_id, task_id, user_id, scheduled_time, status,
   intended_local_date, intended_local_time, intended_timezone, evidence_class)
  VALUES (rem, task, u, now() - interval '1 minute', 'pending', current_date, localtime, 'UTC',
   'staging_synthetic');
 claim := public.claim_reminder_delivery(rem, u, 'delivery-022');
 BEGIN
  PERFORM public.finish_reminder_delivery_v2((claim #>> '{attempt,attempt_id}')::UUID, rem, u,
   'accepted', NULL, 'do_not_retry', 'telegram', 'not-a-number');
  RAISE EXCEPTION 'non-numeric Telegram ref accepted';
 EXCEPTION WHEN raise_exception THEN
  IF SQLERRM <> 'accepted_delivery_requires_message_id' THEN RAISE; END IF;
 END;
 PERFORM public.finish_reminder_delivery_v2((claim #>> '{attempt,attempt_id}')::UUID, rem, u,
  'accepted', NULL, 'do_not_retry', 'fake2', 'msg-abc');
 IF NOT EXISTS (SELECT 1 FROM public.reminders WHERE reminder_id = rem AND status = 'sent'
   AND delivery_channel = 'fake2' AND channel_message_ref = 'msg-abc' AND telegram_message_id IS NULL)
 THEN RAISE EXCEPTION 'non-Telegram delivery proof not recorded'; END IF;
END $$;

-- Telegram v2 writes both proofs; retries leave no proof; v1 dual-writes during the transition;
-- a later non-Telegram delivery clears stale Telegram proof.
DO $$ DECLARE u UUID; task UUID := gen_random_uuid(); rem UUID := gen_random_uuid();
 claim JSONB; BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES (91022010) RETURNING user_id INTO u;
 INSERT INTO public.tasks(task_id, user_id, title, status) VALUES (task, u, 'Synthetic 022 tg', 'pending');
 INSERT INTO public.reminders(reminder_id, task_id, user_id, scheduled_time, status,
   intended_local_date, intended_local_time, intended_timezone, evidence_class)
  VALUES (rem, task, u, now() - interval '1 minute', 'pending', current_date, localtime, 'UTC',
   'staging_synthetic');
 claim := public.claim_reminder_delivery(rem, u, 'delivery-022-retry');
 PERFORM public.finish_reminder_delivery_v2((claim #>> '{attempt,attempt_id}')::UUID, rem, u,
  'rejected', 'provider_timeout', 'retry', 'telegram', NULL);
 IF NOT EXISTS (SELECT 1 FROM public.reminders WHERE reminder_id = rem AND status = 'pending'
   AND telegram_message_id IS NULL AND channel_message_ref IS NULL AND delivery_channel IS NULL)
 THEN RAISE EXCEPTION 'retry outcome recorded proof'; END IF;
 claim := public.claim_reminder_delivery(rem, u, 'delivery-022-v1');
 PERFORM public.finish_reminder_delivery((claim #>> '{attempt,attempt_id}')::UUID, rem, u,
  'accepted', NULL, 'do_not_retry', 4242);
 IF NOT EXISTS (SELECT 1 FROM public.reminders WHERE reminder_id = rem AND status = 'sent'
   AND telegram_message_id = 4242 AND delivery_channel = 'telegram' AND channel_message_ref = '4242')
 THEN RAISE EXCEPTION 'v1 did not dual-write'; END IF;
 UPDATE public.reminders SET status = 'pending' WHERE reminder_id = rem;
 claim := public.claim_reminder_delivery(rem, u, 'delivery-022-tg');
 PERFORM public.finish_reminder_delivery_v2((claim #>> '{attempt,attempt_id}')::UUID, rem, u,
  'accepted', NULL, 'do_not_retry', 'telegram', '4343');
 IF NOT EXISTS (SELECT 1 FROM public.reminders WHERE reminder_id = rem
   AND telegram_message_id = 4343 AND delivery_channel = 'telegram' AND channel_message_ref = '4343')
 THEN RAISE EXCEPTION 'Telegram v2 proof not recorded'; END IF;
 INSERT INTO public.pairing_tokens(token, supabase_auth_id, expires_at)
  VALUES ('t022-x', gen_random_uuid(), now() + interval '10 minutes');
 UPDATE public.user_profiles p SET supabase_auth_id = t.supabase_auth_id
  FROM public.pairing_tokens t WHERE t.token = 't022-x' AND p.user_id = u;
 PERFORM public.complete_pairing_v2('t022-x', 'fake2', 'ext-tg-user');
 UPDATE public.reminders SET status = 'pending' WHERE reminder_id = rem;
 claim := public.claim_reminder_delivery(rem, u, 'delivery-022-switch');
 PERFORM public.finish_reminder_delivery_v2((claim #>> '{attempt,attempt_id}')::UUID, rem, u,
  'accepted', NULL, 'do_not_retry', 'fake2', 'msg-xyz');
 IF NOT EXISTS (SELECT 1 FROM public.reminders WHERE reminder_id = rem
   AND telegram_message_id IS NULL AND delivery_channel = 'fake2')
 THEN RAISE EXCEPTION 'stale Telegram proof kept'; END IF;
END $$;

-- The common case: an existing Telegram + dashboard profile adds a second app. It links, the
-- primary stays Telegram, and a conflicting attempt leaves its token unconsumed.
DO $$ DECLARE u UUID; auth UUID := gen_random_uuid(); BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id, supabase_auth_id) VALUES (91022020, auth)
  RETURNING user_id INTO u;
 INSERT INTO public.pairing_tokens(token, supabase_auth_id, expires_at)
  VALUES ('t022-g', auth, now() + interval '10 minutes'),
         ('t022-h', auth, now() + interval '10 minutes');
 IF public.complete_pairing_v2('t022-g', 'fake2', 'ext-20')->>'status' <> 'paired'
 THEN RAISE EXCEPTION 'legacy profile Pairing failed'; END IF;
 IF (SELECT primary_channel FROM public.user_profiles WHERE user_id = u) <> 'telegram'
  OR (SELECT count(*) FROM public.channel_identities WHERE user_id = u) <> 2
 THEN RAISE EXCEPTION 'legacy profile did not link a second app'; END IF;
 IF public.complete_pairing_v2('t022-h', 'fake2', 'ext-1')->>'status' <> 'conflict'
 THEN RAISE EXCEPTION 'foreign identity linked'; END IF;
 IF (SELECT consumed FROM public.pairing_tokens WHERE token = 't022-h')
 THEN RAISE EXCEPTION 'conflict consumed the token'; END IF;
 BEGIN
  PERFORM public.complete_pairing_v2('t022-h', 'telegram', '-0091022020');
  RAISE EXCEPTION 'non-canonical Telegram id accepted';
 EXCEPTION WHEN raise_exception THEN
  IF SQLERRM <> 'invalid_channel_identity' THEN RAISE; END IF;
 END;
END $$;

-- Clearing telegram_chat_id removes the mirrored identity; deleting a profile cascades.
DO $$ DECLARE u UUID; BEGIN
 SELECT user_id INTO u FROM public.channel_identities WHERE channel = 'fake2' AND external_id = 'ext-20';
 UPDATE public.user_profiles SET primary_channel = 'fake2', telegram_chat_id = NULL WHERE user_id = u;
 SET CONSTRAINTS ALL IMMEDIATE;
 IF EXISTS (SELECT 1 FROM public.channel_identities WHERE user_id = u AND channel = 'telegram')
 THEN RAISE EXCEPTION 'mirror did not delete the Telegram identity'; END IF;
 SET CONSTRAINTS ALL DEFERRED;
 DELETE FROM public.user_profiles WHERE user_id = u;
 SET CONSTRAINTS ALL IMMEDIATE;
 IF EXISTS (SELECT 1 FROM public.channel_identities WHERE user_id = u)
 THEN RAISE EXCEPTION 'profile delete did not cascade'; END IF;
 SET CONSTRAINTS ALL DEFERRED;
END $$;

-- Privileges: reads only for the service credential; no participant-facing access.
DO $$ BEGIN
 IF has_table_privilege('service_role', 'public.channel_identities', 'INSERT')
  OR has_table_privilege('service_role', 'public.channel_identities', 'UPDATE')
  OR has_table_privilege('service_role', 'public.channel_identities', 'DELETE')
  OR NOT has_table_privilege('service_role', 'public.channel_identities', 'SELECT')
  OR has_table_privilege('authenticated', 'public.channel_identities', 'SELECT')
  OR has_table_privilege('service_role', 'public.channel_update_claims', 'SELECT')
  OR has_function_privilege('anon', 'public.complete_pairing_v2(text,text,text)', 'EXECUTE')
  OR has_function_privilege('authenticated', 'public.set_primary_channel(uuid,text)', 'EXECUTE')
  OR NOT has_function_privilege('service_role', 'public.claim_channel_update(text,text,text,text)', 'EXECUTE')
 THEN RAISE EXCEPTION '022 privileges wrong'; END IF;
END $$;
ROLLBACK;
