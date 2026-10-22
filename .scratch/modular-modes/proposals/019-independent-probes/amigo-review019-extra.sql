BEGIN;
DO $$ DECLARE u UUID; p UUID; token TEXT; r JSONB; cfg JSONB; d public.coaching_delivery_outbox%ROWTYPE; old_token UUID; auth UUID:=gen_random_uuid(); test_task UUID; test_reminder UUID; BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id,timezone,wake_time,sleep_time) VALUES(910199991,'UTC','00:00','00:00') RETURNING user_id INTO u;
 UPDATE public.user_profiles SET supabase_auth_id=auth WHERE user_id=u;
 INSERT INTO public.tasks(user_id,title,status) VALUES(u,'Private synthetic test','completed') RETURNING task_id INTO test_task;
 INSERT INTO public.reminders(user_id,task_id,scheduled_time,status,telegram_message_id,intended_local_date,intended_local_time,intended_timezone) VALUES(u,test_task,clock_timestamp()-interval '1 day','acknowledged',1,(clock_timestamp() AT TIME ZONE 'UTC')::date-1,'12:00','UTC') RETURNING reminder_id INTO test_reminder;
 INSERT INTO public.activation_journeys(auth_id,policy_version,acknowledged_at,profile_completed_at,test_task_id,test_reminder_id,test_confirmed_at) VALUES(auth,'fictional-test-policy',clock_timestamp(),clock_timestamp(),test_task,test_reminder,clock_timestamp());
 IF (public.get_activation_state(auth)->>'completed')::boolean IS NOT TRUE THEN RAISE EXCEPTION 'independent Activation fixture failed'; END IF;
 cfg:='{"goal":"Synthetic","success_measure":"Chosen","check_in_days":[1,2,3,4,5,6,7],"check_in_time":"18:00","timezone":"UTC"}';
 r:=public.coaching_program_command(u,NULL,NULL,'draft','draft','draft',cfg); p:=(r->'program'->>'program_id')::UUID;
 token:=public.issue_coaching_approval(u,p,1); PERFORM public.confirm_coaching_approval(u,token,'approve','approve');
 PERFORM public.grant_mode(u,'coach','independent-review','fictional-only');
 PERFORM public.set_coaching_consent(u,'coaching-v1');
 r:=public.enqueue_coaching_delivery(u,p,2,'review:claim',(clock_timestamp() AT TIME ZONE 'UTC')::DATE,'check_in',clock_timestamp()-interval '1 second');
 IF r->>'status'<>'queued' THEN RAISE EXCEPTION 'fixture not queued: %',r; END IF;
 SELECT * INTO d FROM public.claim_coaching_deliveries('review-first',1); old_token:=d.claim_token;
 IF public.mark_coaching_dispatch(u,d.delivery_key,gen_random_uuid()) THEN RAISE EXCEPTION 'wrong claim token dispatched'; END IF;
 UPDATE public.coaching_delivery_outbox SET claimed_at=clock_timestamp()-interval '6 minutes' WHERE user_id=u;
 SELECT * INTO d FROM public.claim_coaching_deliveries('review-second',1);
 IF d.claim_token=old_token OR public.mark_coaching_dispatch(u,d.delivery_key,old_token) THEN RAISE EXCEPTION 'old worker crossed new lease'; END IF;
 PERFORM public.set_coaching_consent(u,NULL);
 IF public.mark_coaching_dispatch(u,d.delivery_key,d.claim_token) THEN RAISE EXCEPTION 'withdrawal allowed dispatch'; END IF;
 IF (SELECT state FROM public.coaching_delivery_outbox WHERE user_id=u)<>'cancelled' THEN RAISE EXCEPTION 'withdrawal did not cancel'; END IF;
 IF EXISTS(SELECT 1 FROM public.proactive_reservations WHERE user_id=u AND kind='coaching' AND state<>'cancelled') THEN RAISE EXCEPTION 'withdrawal capacity retained'; END IF;
END $$;
DO $$ DECLARE t TEXT; f TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['proactive_reservations','proactive_processing_consents','coaching_delivery_replies','coaching_delivery_outbox'] LOOP
  IF has_table_privilege('anon','public.'||t,'SELECT,INSERT,UPDATE,DELETE') OR
     has_table_privilege('authenticated','public.'||t,'SELECT,INSERT,UPDATE,DELETE') OR
     has_table_privilege('service_role','public.'||t,'INSERT,UPDATE,DELETE') THEN RAISE EXCEPTION 'direct table privilege: %',t; END IF;
 END LOOP;
 FOR f IN SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND proname IN
 ('reserve_proactive_delivery','release_proactive_delivery','set_proactive_consent','get_proactive_consent','set_coaching_consent','has_coaching_consent','note_coaching_reply','get_coaching_delivery_history','enqueue_coaching_delivery','claim_coaching_deliveries','mark_coaching_dispatch','finish_coaching_delivery') LOOP
  IF has_function_privilege('anon',f,'EXECUTE') OR has_function_privilege('authenticated',f,'EXECUTE') OR NOT has_function_privilege('service_role',f,'EXECUTE') THEN RAISE EXCEPTION 'RPC role privilege: %',f; END IF;
 END LOOP;
END $$;
ROLLBACK;
