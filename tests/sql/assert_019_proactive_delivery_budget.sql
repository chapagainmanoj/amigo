\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE u UUID; other_u UUID; p UUID; r JSONB; d RECORD; token UUID; n INT; key TEXT;
 auth UUID:='00000000-0000-0000-0000-000000019001'; task_id UUID; reminder_id UUID;
BEGIN
 IF public.get_app_schema_version()<>19 THEN RAISE EXCEPTION '019 not reported'; END IF;
 INSERT INTO public.user_profiles(telegram_chat_id,timezone,daily_message_budget,wake_time,sleep_time)
 VALUES(91019001,'UTC',2,'00:00','00:00') RETURNING user_id INTO u;
 INSERT INTO public.user_profiles(telegram_chat_id,timezone)
 VALUES(91019002,'UTC') RETURNING user_id INTO other_u;
 r:=public.reserve_proactive_delivery(u,'reminder:first','reminder',date_trunc('minute',clock_timestamp()));
 IF r->>'status'<>'reserved' THEN RAISE EXCEPTION 'first reservation failed'; END IF;
 IF public.reserve_proactive_delivery(u,'reminder:first','reminder',
   (r->'reservation'->>'scheduled_at')::timestamptz)<>jsonb_set(r,'{status}','"already_reserved"')
 THEN RAISE EXCEPTION 'reservation replay changed'; END IF;
 PERFORM public.reserve_proactive_delivery(u,'reminder:second','reminder',clock_timestamp());
 IF public.reserve_proactive_delivery(u,'reminder:third','reminder',clock_timestamp())->>'status'<>'budget_exhausted'
 THEN RAISE EXCEPTION 'shared cap bypassed'; END IF;
 IF NOT public.release_proactive_delivery(u,'reminder:second') THEN RAISE EXCEPTION 'release failed'; END IF;
 IF public.release_proactive_delivery(other_u,'reminder:first') THEN RAISE EXCEPTION 'cross-owner release'; END IF;
 UPDATE public.user_profiles SET supabase_auth_id=auth WHERE user_id=u;
 INSERT INTO public.tasks(user_id,title,status) VALUES(u,'Private test','completed') RETURNING tasks.task_id INTO task_id;
 INSERT INTO public.reminders(user_id,task_id,scheduled_time,status,telegram_message_id,
 intended_local_date,intended_local_time,intended_timezone)
 VALUES(u,task_id,clock_timestamp()-interval '1 day','acknowledged',1,
 (clock_timestamp() AT TIME ZONE 'UTC')::date-1,
 (clock_timestamp() AT TIME ZONE 'UTC')::time,'UTC')
 RETURNING reminders.reminder_id INTO reminder_id;
 INSERT INTO public.activation_journeys(auth_id,policy_version,acknowledged_at,profile_completed_at,
 test_task_id,test_reminder_id,test_confirmed_at)
 VALUES(auth,'fictional-test-policy',clock_timestamp(),clock_timestamp(),task_id,reminder_id,clock_timestamp());
 IF (public.get_activation_state(auth)->>'completed')::boolean IS NOT TRUE THEN
   RAISE EXCEPTION 'Activation fixture incomplete'; END IF;

 INSERT INTO public.coaching_programs(user_id,goal,success_measure,check_in_days,check_in_time,
 timezone,state,starts_at,ends_at) VALUES(u,'Fictional goal','My measure',ARRAY[1,2,3,4,5,6,7],
 to_char(clock_timestamp() AT TIME ZONE 'UTC','HH24:MI'),'UTC','active',
 clock_timestamp()-interval '1 day',clock_timestamp()+interval '13 days') RETURNING program_id INTO p;
 PERFORM public.grant_mode(u,'coach','sql-test','Fictional test');
 key:='coach:'||p||':'||(clock_timestamp() AT TIME ZONE 'UTC')::date;
 r:=public.enqueue_coaching_delivery(u,p,1,key,(clock_timestamp() AT TIME ZONE 'UTC')::date,
 'check_in',date_trunc('minute',clock_timestamp()));
 IF r->>'status'<>'unavailable' THEN RAISE EXCEPTION 'missing consent did not deny'; END IF;
 PERFORM public.set_proactive_consent(u,'reflect-v1','reflect-sensitive-processing-v1','US');
 IF public.has_coaching_consent(u) THEN RAISE EXCEPTION 'Reflect consent authorized Coach'; END IF;
 IF public.get_proactive_consent(other_u,'reflect-v1') IS NOT NULL THEN RAISE EXCEPTION 'cross-owner consent'; END IF;
 PERFORM public.set_coaching_consent(u,'coaching-v1');
 r:=public.enqueue_coaching_delivery(u,p,1,key,(clock_timestamp() AT TIME ZONE 'UTC')::date,
 'check_in',date_trunc('minute',clock_timestamp()));
 IF r->>'status'<>'queued' THEN RAISE EXCEPTION 'valid coaching queue failed %',r->>'status'; END IF;
 IF public.enqueue_coaching_delivery(u,p,1,key,(clock_timestamp() AT TIME ZONE 'UTC')::date,
 'check_in',date_trunc('minute',clock_timestamp()))->>'status'<>'already_queued'
 THEN RAISE EXCEPTION 'duplicate day queued'; END IF;
 SELECT * INTO d FROM public.claim_coaching_deliveries('sql-worker',25) WHERE delivery_key=key;
 token:=d.claim_token;
 IF token IS NULL THEN RAISE EXCEPTION 'outbox not claimed'; END IF;
 IF public.mark_coaching_dispatch(other_u,key,token) THEN RAISE EXCEPTION 'cross-owner dispatch'; END IF;
 IF public.mark_coaching_dispatch(u,key,gen_random_uuid()) THEN RAISE EXCEPTION 'unfenced dispatch'; END IF;
 IF NOT public.mark_coaching_dispatch(u,key,token) THEN RAISE EXCEPTION 'valid dispatch denied'; END IF;
 IF public.release_proactive_delivery(u,key) THEN RAISE EXCEPTION 'dispatched budget released'; END IF;
 IF NOT public.finish_coaching_delivery(u,key,token,'uncertain') THEN RAISE EXCEPTION 'finish denied'; END IF;
 IF public.finish_coaching_delivery(u,key,token,'accepted') THEN RAISE EXCEPTION 'terminal replay changed'; END IF;
 SELECT count(*) INTO n FROM public.claim_coaching_deliveries('sql-worker-restart',25) WHERE delivery_key=key;
 IF n<>0 THEN RAISE EXCEPTION 'uncertain send retried'; END IF;
 PERFORM public.set_coaching_consent(u,NULL);
 IF public.has_coaching_consent(u) THEN RAISE EXCEPTION 'withdrawal failed'; END IF;
 IF public.get_coaching_delivery_history(other_u,p)->'deliveries'<>'[]'::jsonb THEN
  RAISE EXCEPTION 'cross-owner delivery history'; END IF;
 IF public.note_coaching_reply(other_u,p) THEN RAISE EXCEPTION 'cross-owner reply reset'; END IF;
 IF NOT public.note_coaching_reply(u,p) THEN RAISE EXCEPTION 'owned reply reset denied'; END IF;
END $$;
DO $$ DECLARE t TEXT; fn TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['proactive_reservations','proactive_processing_consents',
   'coaching_delivery_outbox','coaching_delivery_replies'] LOOP
  IF NOT (SELECT relrowsecurity FROM pg_class WHERE oid=('public.'||t)::regclass) THEN
   RAISE EXCEPTION '019 RLS missing'; END IF;
  IF has_table_privilege('authenticated','public.'||t,'SELECT,INSERT,UPDATE,DELETE')
    OR has_table_privilege('service_role','public.'||t,'INSERT,UPDATE,DELETE') THEN
   RAISE EXCEPTION '019 direct client mutation or client read allowed'; END IF;
 END LOOP;
 FOREACH fn IN ARRAY ARRAY['reserve_proactive_delivery(uuid,text,text,timestamptz,uuid)',
  'set_proactive_consent(uuid,text,text,text,boolean)','mark_coaching_dispatch(uuid,text,uuid)',
  'claim_coaching_deliveries(text,integer)'] LOOP
  IF has_function_privilege('authenticated','public.'||fn,'EXECUTE')
   OR has_function_privilege('anon','public.'||fn,'EXECUTE')
   OR NOT has_function_privilege('service_role','public.'||fn,'EXECUTE') THEN
   RAISE EXCEPTION '019 RPC grants incorrect'; END IF;
  IF NOT (SELECT prosecdef AND 'search_path=""'=ANY(proconfig) FROM pg_proc
    WHERE oid=('public.'||fn)::regprocedure) THEN RAISE EXCEPTION '019 RPC not hardened'; END IF;
 END LOOP;
END $$;
ROLLBACK;
