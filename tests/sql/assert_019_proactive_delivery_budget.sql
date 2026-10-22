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
 r:=public.reserve_proactive_delivery(u,'recovery:first','recovery',date_trunc('minute',clock_timestamp()));
 IF r->>'status'<>'reserved' THEN RAISE EXCEPTION 'first reservation failed'; END IF;
 IF public.reserve_proactive_delivery(u,'recovery:first','recovery',
   (r->'reservation'->>'scheduled_at')::timestamptz)<>jsonb_set(r,'{status}','"already_reserved"')
 THEN RAISE EXCEPTION 'reservation replay changed'; END IF;
 PERFORM public.reserve_proactive_delivery(u,'recovery:second','recovery',clock_timestamp());
 IF public.reserve_proactive_delivery(u,'recovery:third','recovery',clock_timestamp())->>'status'<>'budget_exhausted'
 THEN RAISE EXCEPTION 'shared cap bypassed'; END IF;
 IF NOT public.release_proactive_delivery(u,'recovery:second') THEN RAISE EXCEPTION 'release failed'; END IF;
 IF public.release_proactive_delivery(other_u,'recovery:first') THEN RAISE EXCEPTION 'cross-owner release'; END IF;
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
 -- Cadence stays in the Program's UTC day; quiet hours follow the current profile zone.
 UPDATE public.user_profiles SET timezone='Etc/GMT+12',
 wake_time=to_char((clock_timestamp() AT TIME ZONE 'UTC')-interval '30 minutes','HH24:MI')::time,
 sleep_time=to_char((clock_timestamp() AT TIME ZONE 'UTC')+interval '30 minutes','HH24:MI')::time
 WHERE user_id=u;
 IF public.mark_coaching_dispatch(u,key,token) THEN
   RAISE EXCEPTION 'profile travel quiet hours ignored'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.coaching_delivery_outbox WHERE user_id=u
   AND delivery_key=key AND state='cancelled') THEN
   RAISE EXCEPTION 'quiet travel occurrence not cancelled'; END IF;
 -- Reset this fixture's cancelled claim to isolate the inverse case: profile awake,
 -- Program wall time quiet. This direct mutation is test-owner setup, never runtime behavior.
 UPDATE public.coaching_delivery_outbox SET state='claimed',finished_at=NULL
 WHERE user_id=u AND delivery_key=key;
 UPDATE public.proactive_reservations SET state='reserved' WHERE user_id=u AND delivery_key=key;
 UPDATE public.user_profiles SET
 wake_time=to_char((clock_timestamp() AT TIME ZONE timezone)-interval '30 minutes','HH24:MI')::time,
 sleep_time=to_char((clock_timestamp() AT TIME ZONE timezone)+interval '30 minutes','HH24:MI')::time
 WHERE user_id=u;
 -- Existing consumed Coach capacity survives Program deletion (program_id NULL).
 INSERT INTO public.proactive_reservations(user_id,delivery_key,kind,scheduled_at,timezone,local_day,state)
 VALUES(u,'travel:consumed','coaching',clock_timestamp(),'Etc/GMT+12',
 (clock_timestamp() AT TIME ZONE 'Etc/GMT+12')::date,'accepted');
 IF public.mark_coaching_dispatch(u,key,token) THEN
   RAISE EXCEPTION 'dispatch ignored another Coach in current profile day'; END IF;
 DELETE FROM public.proactive_reservations WHERE user_id=u AND delivery_key='travel:consumed';
 UPDATE public.coaching_delivery_outbox SET state='claimed',finished_at=NULL
 WHERE user_id=u AND delivery_key=key;
 UPDATE public.proactive_reservations SET state='reserved' WHERE user_id=u AND delivery_key=key;
 UPDATE public.user_profiles SET daily_message_budget=0 WHERE user_id=u;
 IF public.mark_coaching_dispatch(u,key,token) THEN
   RAISE EXCEPTION 'dispatch ignored reduced shared budget'; END IF;
 UPDATE public.user_profiles SET daily_message_budget=2 WHERE user_id=u;
 UPDATE public.coaching_delivery_outbox SET state='claimed',finished_at=NULL
 WHERE user_id=u AND delivery_key=key;
 UPDATE public.proactive_reservations SET state='reserved' WHERE user_id=u AND delivery_key=key;
 IF NOT public.mark_coaching_dispatch(u,key,token) THEN
   RAISE EXCEPTION 'awake profile denied by Program timezone'; END IF;
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
DO $$ DECLARE u UUID; at TIMESTAMPTZ:=clock_timestamp(); BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id,timezone,daily_message_budget)
 VALUES(91019003,'UTC',4) RETURNING user_id INTO u;
 IF public.reserve_proactive_delivery(u,'coach:old','coaching',at)->>'status'<>'reserved'
 THEN RAISE EXCEPTION 'first Coach admission failed'; END IF;
 IF public.reserve_proactive_delivery(u,'coach:new-program','coaching',at)->>'status'<>'budget_exhausted'
 THEN RAISE EXCEPTION 'second Coach admitted across Programs'; END IF;
 IF NOT public.release_proactive_delivery(u,'coach:old') THEN RAISE EXCEPTION 'unused Coach not released'; END IF;
 IF public.reserve_proactive_delivery(u,'coach:new-program','coaching',at)->>'status'<>'reserved'
 THEN RAISE EXCEPTION 'released Coach cannot retry'; END IF;
 UPDATE public.proactive_reservations SET state='accepted' WHERE user_id=u AND delivery_key='coach:new-program';
 IF public.reserve_proactive_delivery(u,'coach:after-delete','coaching',at)->>'status'<>'budget_exhausted'
 THEN RAISE EXCEPTION 'accepted Coach with NULL Program did not retain cap'; END IF;
 UPDATE public.proactive_reservations SET state='uncertain' WHERE user_id=u AND delivery_key='coach:new-program';
 IF public.reserve_proactive_delivery(u,'coach:after-uncertain','coaching',at)->>'status'<>'budget_exhausted'
 THEN RAISE EXCEPTION 'uncertain Coach with NULL Program did not retain cap'; END IF;
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
DO $$ DECLARE u UUID; task UUID; rid UUID; later_id UUID; v BIGINT; result JSONB;
 auth UUID:='00000000-0000-0000-0000-000000019099'; at TIMESTAMPTZ:=clock_timestamp();
BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id,timezone,daily_message_budget,supabase_auth_id)
 VALUES(91019099,'UTC',0,auth) RETURNING user_id INTO u;
 INSERT INTO public.tasks(user_id,title) VALUES(u,'Requested task') RETURNING task_id INTO task;
 -- Direct writes, canonical scheduling, replacement and Later all ignore a zero budget.
 INSERT INTO public.reminders(user_id,task_id,scheduled_time,intended_local_date,intended_local_time,intended_timezone)
 VALUES(u,task,at,(at AT TIME ZONE 'UTC')::date,(at AT TIME ZONE 'UTC')::time,'UTC')
 RETURNING reminder_id INTO rid;
 UPDATE public.reminders SET status='sending' WHERE reminder_id=rid;
 UPDATE public.reminders SET status='sent',telegram_message_id=99 WHERE reminder_id=rid;
 result:=public.schedule_reminder_command(u,'requested',repeat('a',64),task,NULL,at,
 (at AT TIME ZONE 'UTC')::date,(at AT TIME ZONE 'UTC')::time,'UTC');
 later_id:=(result->'reminder'->>'reminder_id')::UUID;
 result:=public.schedule_reminder_command(u,'replace',repeat('a',64),task,later_id,at+interval '1 hour',
 (at AT TIME ZONE 'UTC')::date,((at+interval '1 hour') AT TIME ZONE 'UTC')::time,'UTC');
 later_id:=(result->'reminder'->>'reminder_id')::UUID;
 SELECT version INTO v FROM public.tasks WHERE task_id=task;
 result:=public.apply_later_command(u,'later',repeat('a',64),later_id,v,1,at+interval '2 hours',
 (at AT TIME ZONE 'UTC')::date,((at+interval '2 hours') AT TIME ZONE 'UTC')::time,'UTC',FALSE,NULL);
 PERFORM public.acknowledge_activation_terms(auth,'fictional-policy');
 PERFORM public.update_activation_profile(auth,'Fictional','UTC','07:00','23:00');
 PERFORM public.create_activation_test_command(u,'activation',repeat('a',64),'Private test',FALSE,at,
 (at AT TIME ZONE 'UTC')::date,(at AT TIME ZONE 'UTC')::time,'UTC');
 IF EXISTS(SELECT 1 FROM public.proactive_reservations WHERE user_id=u) THEN
 RAISE EXCEPTION 'participant request consumed proactive capacity'; END IF;
 IF public.reserve_proactive_delivery(u,'blocked','recovery',at)->>'status'<>'budget_exhausted'
 THEN RAISE EXCEPTION 'zero proactive budget ignored'; END IF;
 UPDATE public.user_profiles SET daily_message_budget=1 WHERE user_id=u;
 PERFORM public.reserve_proactive_delivery(u,'summary','recovery',at);
 IF public.mark_proactive_dispatch(gen_random_uuid(),'summary') THEN RAISE EXCEPTION 'foreign recovery dispatch'; END IF;
 IF NOT public.mark_proactive_dispatch(u,'summary') OR public.mark_proactive_dispatch(u,'summary')
 THEN RAISE EXCEPTION 'recovery fence'; END IF;
 IF public.release_proactive_delivery(u,'summary') THEN RAISE EXCEPTION 'dispatched recovery released'; END IF;
 IF NOT public.finish_proactive_delivery(u,'summary','uncertain')
 OR public.finish_proactive_delivery(u,'summary','accepted') THEN RAISE EXCEPTION 'recovery terminal replay'; END IF;
 IF public.reserve_proactive_delivery(u,'next','recovery',at)->>'status'<>'budget_exhausted'
 THEN RAISE EXCEPTION 'uncertain recovery did not count'; END IF;
END $$;
ROLLBACK;
