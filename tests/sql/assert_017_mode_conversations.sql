\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE u UUID; other_u UUID; src UUID; dst UUID; wrong_dst UUID; h UUID; first_token UUID;
        r JSONB; clock_at TEXT; current_token UUID;
BEGIN
 IF public.get_app_schema_version() <> 17 THEN RAISE EXCEPTION '017 not reported'; END IF;
 INSERT INTO public.user_profiles(telegram_chat_id,supabase_auth_id)
   VALUES(91017001,'00000000-0000-0000-0000-000000017001') RETURNING user_id INTO u;
 INSERT INTO public.user_profiles(telegram_chat_id,supabase_auth_id)
   VALUES(91017002,'00000000-0000-0000-0000-000000017002') RETURNING user_id INTO other_u;
 PERFORM set_config('amigo.test_user',u::TEXT,TRUE);
 PERFORM public.save_mode_conversation(u,'daily','telegram','{"chat_id":91017001,"thread_id":1}');
 PERFORM public.save_mode_conversation(u,'daily','telegram','{"chat_id":91017001,"thread_id":2}',TRUE);
 -- Ordinary concurrent creation must not overwrite the existing canonical endpoint.
 r := public.save_mode_conversation(u,'daily','telegram','{"chat_id":91017001,"thread_id":3}');
 IF r->'endpoint' <> '{"chat_id":91017001,"thread_id":1}'::jsonb THEN
   RAISE EXCEPTION 'canonical endpoint was replaced while open'; END IF;
 IF (SELECT count(*) FROM public.mode_conversations WHERE user_id=u) <> 1
    OR (SELECT count(*) FROM public.mode_conversation_endpoints WHERE user_id=u) <> 2 THEN
   RAISE EXCEPTION 'aliases changed canonical cardinality'; END IF;
 BEGIN
   PERFORM public.save_mode_conversation(other_u,'coach','telegram','{"chat_id":91017001,"thread_id":2}');
   RAISE EXCEPTION 'alias endpoint reassigned across owner/mode';
 EXCEPTION WHEN raise_exception THEN
   IF SQLERRM <> 'conversation_endpoint_conflict' THEN RAISE; END IF;
 END;
 PERFORM public.save_mode_conversation(other_u,'daily','cli','{"recipient":"other"}');
 PERFORM public.close_mode_conversation(u,'daily','telegram');
 IF EXISTS(SELECT 1 FROM public.mode_conversation_endpoints WHERE user_id=u AND closed_at IS NULL) THEN
   RAISE EXCEPTION 'aliases were not closed'; END IF;
 PERFORM public.save_mode_conversation(u,'daily','telegram','{"chat_id":91017001,"thread_id":4}');
 IF (SELECT endpoint FROM public.mode_conversations WHERE user_id=u AND channel='telegram') <>
    '{"chat_id":91017001,"thread_id":4}'::jsonb THEN RAISE EXCEPTION 'closed canonical not replaced'; END IF;

 INSERT INTO public.sessions(user_id,mode_id,active_mode_id) VALUES(u,'coach','coach') RETURNING session_id INTO src;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'daily') RETURNING session_id INTO dst;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(other_u,'daily') RETURNING session_id INTO wrong_dst;
 PERFORM public.grant_mode(u,'coach','owner','trial');
 r:=public.create_mode_handoff(u,src,'coach','daily','Fictional carried request');
 h:=(r->'handoff'->>'handoff_id')::UUID;
 IF public.claim_handoff_execution(u,h,'worker',dst)->>'status' <> 'unavailable' THEN
   RAISE EXCEPTION 'unconfirmed payload was claimable'; END IF;
 PERFORM public.resolve_mode_handoff(u,src,h,TRUE);
 IF public.claim_handoff_execution(other_u,h,'worker',wrong_dst)->>'status' <> 'unavailable' THEN
   RAISE EXCEPTION 'execution bound cross-owner Session'; END IF;
 r:=public.claim_handoff_execution(u,h,'worker',dst);
 IF r->>'status' <> 'claimed' OR r->'handoff'->>'carried_request' <> 'Fictional carried request' THEN
   RAISE EXCEPTION 'confirmed handoff was not claimed'; END IF;
 first_token:=(r->'handoff'->>'execution_claim_token')::UUID;
 clock_at:=r->'handoff'->>'execution_clock_at';
 IF public.claim_handoff_execution(u,h,'double-tap',dst)->>'status' <> 'busy' THEN
   RAISE EXCEPTION 'live execution lease was stolen'; END IF;
 IF NOT public.save_handoff_execution_plan(u,h,first_token,'[{"step":1}]')
    OR NOT public.save_handoff_execution_plan(u,h,first_token,'[{"step":1}]')
    OR public.save_handoff_execution_plan(u,h,first_token,'[{"step":2}]')
    OR public.save_handoff_execution_plan(u,h,first_token,'[]') THEN
   RAISE EXCEPTION 'plan append-only/idempotence contract failed'; END IF;
 UPDATE public.mode_handoffs SET execution_claimed_at=clock_timestamp()-interval '6 minutes' WHERE handoff_id=h;
 IF public.complete_handoff_execution(u,h,first_token) THEN RAISE EXCEPTION 'expired lease completed'; END IF;
 UPDATE public.sessions SET ended_at=clock_timestamp() WHERE session_id=dst;
 r:=public.claim_handoff_execution(u,h,'recovery');
 current_token:=(r->'handoff'->>'execution_claim_token')::UUID;
 IF r->>'status' <> 'claimed' OR r->'handoff'->>'execution_clock_at' <> clock_at
    OR (r->'handoff'->>'execution_session_id')::UUID <> dst
    OR r->'handoff'->'execution_plan' <> '[{"step":1}]'::jsonb
    OR (r->'handoff'->>'execution_attempts')::INT <> 2 THEN
   RAISE EXCEPTION 'recovery lost stable execution state'; END IF;
 IF public.complete_handoff_execution(u,h,first_token)
    OR public.save_handoff_execution_plan(u,h,first_token,'[{"step":1},{"step":2}]')
    OR public.complete_handoff_execution(other_u,h,current_token)
    OR NOT public.complete_handoff_execution(u,h,current_token)
    OR public.complete_handoff_execution(u,h,current_token) THEN
   RAISE EXCEPTION 'execution fencing/single completion failed'; END IF;
 IF public.claim_handoff_execution(u,h,'late')->>'status' <> 'executed' THEN
   RAISE EXCEPTION 'completed handoff replay accepted'; END IF;
END $$;
DO $$
DECLARE u UUID; outsider UUID; src UUID; dst UUID; wrong_dst UUID; h UUID; last_h UUID;
 row RECORD; r JSONB; old_token UUID; token UUID; i INT; n INT;
BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91017003) RETURNING user_id INTO u;
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91017004) RETURNING user_id INTO outsider;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'coach') RETURNING session_id INTO src;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'daily') RETURNING session_id INTO dst;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'coach') RETURNING session_id INTO wrong_dst;
 FOR i IN 1..26 LOOP
   INSERT INTO public.mode_handoffs(user_id,session_id,source_mode_id,target_mode_id,
     source_grant_required,target_grant_required,carried_request,created_at,expires_at,
     resolved_at,resolution) VALUES(u,src,'coach','daily',FALSE,FALSE,'Fictional request',
     clock_timestamp()+i*interval '1 microsecond',clock_timestamp()+interval '5 minutes',
     clock_timestamp(),'confirmed') RETURNING handoff_id INTO last_h;
 END LOOP;
 SELECT count(*) INTO n FROM public.list_pending_handoff_executions();
 IF n<>25 THEN RAISE EXCEPTION 'recovery first page not full'; END IF;
 FOR row IN SELECT * FROM public.list_pending_handoff_executions() LOOP
   r:=public.claim_handoff_execution(u,row.handoff_id,'drain',wrong_dst);
   IF r->>'status'<>'unavailable' OR (r->>'terminal')::boolean IS NOT TRUE THEN
     RAISE EXCEPTION 'unavailable claim was not terminal'; END IF;
 END LOOP;
 SELECT count(*) INTO n FROM public.list_pending_handoff_executions();
 IF n<>1 OR NOT EXISTS(SELECT 1 FROM public.list_pending_handoff_executions() WHERE handoff_id=last_h)
 THEN RAISE EXCEPTION 'unavailable rows stalled the LIMIT25 recovery queue'; END IF;
 r:=public.claim_handoff_execution(u,last_h,'first',dst);
 old_token:=(r->'handoff'->>'execution_claim_token')::UUID;
 UPDATE public.mode_handoffs SET execution_claimed_at=clock_timestamp()-interval '6 minutes'
 WHERE handoff_id=last_h;
 IF public.fail_handoff_execution(u,last_h,old_token,'execution_failed') THEN
   RAISE EXCEPTION 'expired failure token accepted'; END IF;
 r:=public.claim_handoff_execution(u,last_h,'recovery');
 token:=(r->'handoff'->>'execution_claim_token')::UUID;
 IF public.fail_handoff_execution(outsider,last_h,token,'execution_failed')
 OR public.fail_handoff_execution(u,last_h,old_token,'execution_failed')
 OR public.fail_handoff_execution(u,last_h,token,'private exception text')
 OR NOT public.fail_handoff_execution(u,last_h,token,'execution_failed')
 OR public.fail_handoff_execution(u,last_h,token,'execution_failed')
 OR public.complete_handoff_execution(u,last_h,token)
 OR public.save_handoff_execution_plan(u,last_h,token,'[{"late":true}]') THEN
   RAISE EXCEPTION 'terminal failure was not owned, fenced and single use'; END IF;
 IF public.claim_handoff_execution(u,last_h,'retry')->>'status'<>'failed'
 OR EXISTS(SELECT 1 FROM public.list_pending_handoff_executions()) THEN
   RAISE EXCEPTION 'terminal failed handoff remained recoverable'; END IF;
END $$;
DO $$
DECLARE u UUID; src UUID; dst UUID; h UUID; r JSONB; m JSONB; token UUID;
BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91017005) RETURNING user_id INTO u;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'coach') RETURNING session_id INTO src;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'daily') RETURNING session_id INTO dst;
 INSERT INTO public.mode_handoffs(user_id,session_id,source_mode_id,target_mode_id,
 source_grant_required,target_grant_required,carried_request,expires_at,resolved_at,resolution)
 VALUES(u,src,'coach','daily',FALSE,FALSE,'Fictional request',clock_timestamp()+interval '5 minutes',
 clock_timestamp(),'confirmed') RETURNING handoff_id INTO h;
 r:=public.claim_handoff_execution(u,h,'one',dst);
 token:=(r->'handoff'->>'execution_claim_token')::UUID;
 m:=public.append_handoff_execution_message(u,h,token,'user','Fictional request','telegram');
 IF m IS NULL OR m<>public.append_handoff_execution_message(u,h,token,'user','Fictional request','telegram')
 OR public.append_handoff_execution_message(u,h,token,'user','Changed request','telegram') IS NOT NULL
 THEN RAISE EXCEPTION 'carried message idempotence/content fence'; END IF;
 UPDATE public.mode_handoffs SET execution_claimed_at=clock_timestamp()-interval '6 minutes' WHERE handoff_id=h;
 IF public.append_handoff_execution_message(u,h,token,'assistant','Late output','telegram') IS NOT NULL
 THEN RAISE EXCEPTION 'expired append token accepted'; END IF;
 r:=public.claim_handoff_execution(u,h,'two');
 token:=(r->'handoff'->>'execution_claim_token')::UUID;
 IF m<>public.append_handoff_execution_message(u,h,token,'user','Fictional request','telegram')
 THEN RAISE EXCEPTION 'recovery duplicated carried message'; END IF;
 UPDATE public.mode_handoffs SET execution_claimed_at=clock_timestamp()-interval '6 minutes' WHERE handoff_id=h;
 r:=public.claim_handoff_execution(u,h,'three');
 IF r->>'status'<>'unavailable' OR r->>'terminal'<>'true'
 OR (SELECT execution_attempts FROM public.mode_handoffs WHERE handoff_id=h)<>2
 OR (SELECT count(*) FROM public.messages WHERE session_id=dst)<>1
 THEN RAISE EXCEPTION 'two-attempt terminal cap failed'; END IF;
 IF public.claim_handoff_failure_notice(gen_random_uuid(),h,'attempted')
 OR NOT public.claim_handoff_failure_notice(u,h,'attempted')
 OR public.claim_handoff_failure_notice(u,h,'attempted')
 OR EXISTS(SELECT 1 FROM public.list_pending_handoff_failure_notices() WHERE handoff_id=h)
 THEN RAISE EXCEPTION 'notice owner/single-attempt/queue fence failed'; END IF;
END $$;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000017001',TRUE);
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.mode_conversations) OR EXISTS(
   SELECT 1 FROM public.mode_conversations WHERE user_id<>current_setting('amigo.test_user')::UUID)
   OR EXISTS(SELECT 1 FROM public.mode_conversation_endpoints WHERE user_id<>current_setting('amigo.test_user')::UUID)
 THEN RAISE EXCEPTION 'conversation RLS tenant isolation failed'; END IF;
END $$;
RESET ROLE;
DO $$ DECLARE t TEXT; f TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['mode_conversations','mode_conversation_endpoints'] LOOP
  IF has_table_privilege('anon','public.'||t,'SELECT,INSERT,UPDATE,DELETE')
    OR has_table_privilege('service_role','public.'||t,'INSERT,UPDATE,DELETE')
    OR has_table_privilege('authenticated','public.'||t,'INSERT,UPDATE,DELETE') THEN
   RAISE EXCEPTION 'conversation direct mutation privileges retained'; END IF;
 END LOOP;
 FOREACH f IN ARRAY ARRAY[
  'save_mode_conversation(uuid,text,text,jsonb,boolean)', 'close_mode_conversation(uuid,text,text)',
  'claim_handoff_execution(uuid,uuid,text,uuid)', 'save_handoff_execution_plan(uuid,uuid,uuid,jsonb)',
  'complete_handoff_execution(uuid,uuid,uuid)', 'fail_handoff_execution(uuid,uuid,uuid,text)',
  'list_pending_handoff_executions(integer)',
  'append_handoff_execution_message(uuid,uuid,uuid,text,text,text)',
  'claim_handoff_failure_notice(uuid,uuid,text)',
  'list_pending_handoff_failure_notices(integer)'] LOOP
  IF has_function_privilege('anon','public.'||f,'EXECUTE')
    OR has_function_privilege('authenticated','public.'||f,'EXECUTE')
    OR NOT has_function_privilege('service_role','public.'||f,'EXECUTE') THEN
   RAISE EXCEPTION 'execution RPC role privileges incorrect'; END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_proc WHERE oid=('public.'||f)::regprocedure
                AND prosecdef AND proconfig @> ARRAY['search_path=""']) THEN
   RAISE EXCEPTION 'execution RPC definer/search_path incorrect: %', f; END IF;
 END LOOP;
END $$;
ROLLBACK;
