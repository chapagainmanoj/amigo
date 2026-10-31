\set ON_ERROR_STOP on
BEGIN;
DO $$ DECLARE
 auth UUID := gen_random_uuid(); u UUID; task UUID := gen_random_uuid(); reminder UUID;
 r JSONB; claim JSONB; version BIGINT; at TIMESTAMPTZ := now() + interval '3 hours';
BEGIN
 IF public.get_app_schema_version() <> 23 THEN RAISE EXCEPTION '023 not reported'; END IF;

 -- A participant whose only app is not Telegram gets queued schedule effects with no address.
 INSERT INTO public.pairing_tokens(token, supabase_auth_id, expires_at)
  VALUES ('t023-a', auth, now() + interval '10 minutes');
 IF public.complete_pairing_v2('t023-a', 'fake2', 'ext-023')->>'status' <> 'paired'
 THEN RAISE EXCEPTION 'non-Telegram Pairing failed'; END IF;
 SELECT user_id INTO u FROM public.user_profiles WHERE supabase_auth_id = auth;
 UPDATE public.user_profiles SET timezone = 'UTC' WHERE user_id = u;
 INSERT INTO public.tasks(task_id, user_id, title, status) VALUES (task, u, 'Synthetic 023', 'pending');

 r := public.schedule_reminder_command(u, 'sql-023-schedule', repeat('e', 64), task, NULL, at,
   (at AT TIME ZONE 'UTC')::DATE, (at AT TIME ZONE 'UTC')::TIME, 'UTC');
 reminder := (r->'reminder'->>'reminder_id')::UUID;
 version := (r->>'task_version')::BIGINT;
 IF reminder IS NULL THEN RAISE EXCEPTION '023 schedule returned no Reminder: %', r; END IF;
 IF (SELECT payload ? 'telegram_chat_id' OR payload->>'task_title' <> 'Synthetic 023'
       OR NOT payload ? 'scheduled_time'
     FROM public.scheduler_outbox WHERE effect_key = 'schedule:' || reminder::text)
 THEN RAISE EXCEPTION '023 schedule payload shape wrong'; END IF;

 claim := public.claim_reminder_delivery(reminder, u, 'delivery-023');
 PERFORM public.finish_reminder_delivery_v2((claim #>> '{attempt,attempt_id}')::UUID, reminder, u,
  'accepted', NULL, 'do_not_retry', 'fake2', 'msg-023');
 r := public.apply_later_command(u, 'sql-023-later', repeat('f', 64), reminder, version, 1,
   at + interval '1 hour', ((at + interval '1 hour') AT TIME ZONE 'UTC')::DATE,
   ((at + interval '1 hour') AT TIME ZONE 'UTC')::TIME, 'UTC', FALSE, NULL);
 IF EXISTS (SELECT 1 FROM public.scheduler_outbox
   WHERE user_id = u AND effect_type = 'schedule'
     AND (payload ? 'telegram_chat_id' OR NOT payload ? 'scheduled_time'
          OR payload->>'task_title' <> 'Synthetic 023'))
  OR (SELECT count(*) FROM public.scheduler_outbox WHERE user_id = u AND effect_type = 'schedule') <> 2
 THEN RAISE EXCEPTION '023 later payload shape wrong: %', r; END IF;

 -- The handoff listing no longer exposes a provider address.
 IF (SELECT 'telegram_chat_id' = ANY(proargnames) FROM pg_catalog.pg_proc
     WHERE oid = 'public.list_pending_handoff_executions(integer)'::regprocedure)
  OR NOT has_function_privilege('service_role', 'public.list_pending_handoff_executions(integer)', 'EXECUTE')
  OR has_function_privilege('anon', 'public.list_pending_handoff_executions(integer)', 'EXECUTE')
 THEN RAISE EXCEPTION '023 handoff listing shape or privileges wrong'; END IF;
 PERFORM * FROM public.list_pending_handoff_executions(5);
END $$;
ROLLBACK;
