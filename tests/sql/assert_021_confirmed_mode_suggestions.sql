\set ON_ERROR_STOP on
BEGIN;
DO $$ DECLARE u UUID; outsider UUID; s UUID; s2 UUID; r JSONB; id UUID; BEGIN
 IF public.get_app_schema_version()<>21 THEN RAISE EXCEPTION '021 not reported'; END IF;
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91021001) RETURNING user_id INTO u;
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91021002) RETURNING user_id INTO outsider;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'daily') RETURNING session_id INTO s;
 IF public.create_mode_suggestion(u,s,'coach') IS NOT NULL THEN
 RAISE EXCEPTION 'ungranted offer admitted'; END IF;
 IF public.get_mode_suggestion_preference(u) IS NOT FALSE THEN RAISE EXCEPTION 'suggestions default on'; END IF;
 PERFORM public.set_mode_suggestion_preference(u,TRUE);
 -- Grant flag is trusted service-only input, not model or participant input.
 INSERT INTO public.mode_grants(user_id,mode_id,granted_by,reason,expires_at)
 VALUES(u,'coach','owner','fictional SQL test',now()+interval '1 day');
 IF public.create_mode_suggestion(outsider,s,'coach',FALSE) IS NOT NULL THEN
 RAISE EXCEPTION 'foreign Session accepted'; END IF;
 r:=public.create_mode_suggestion(u,s,'coach'); id:=(r->>'offer_id')::UUID;
 IF id IS NULL OR r ? 'carried_request' THEN RAISE EXCEPTION 'offer missing or contains text'; END IF;
 IF public.create_mode_suggestion(u,s,'coach') IS NOT NULL THEN
 RAISE EXCEPTION 'second Session offer accepted'; END IF;
 IF public.get_mode_suggestion(outsider,id) IS NOT NULL OR
 public.resolve_mode_suggestion(outsider,id,TRUE) IS NOT NULL THEN
 RAISE EXCEPTION 'cross-owner offer access'; END IF;
 r:=public.resolve_mode_suggestion(u,id,TRUE);
 IF r->>'state'<>'confirmed' THEN
 RAISE EXCEPTION 'confirmation failed'; END IF;
 IF public.resolve_mode_suggestion(u,id,TRUE) IS NOT NULL THEN
 RAISE EXCEPTION 'double confirmation accepted'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.sessions WHERE user_id=u AND mode_id='coach'
 AND session_id=(r->>'opened_session_id')::UUID AND active_mode_id='coach')
 OR (SELECT active_mode_id FROM public.sessions WHERE session_id=s)<>'coach'
 OR EXISTS(SELECT 1 FROM public.messages WHERE session_id=(r->>'opened_session_id')::UUID)
 THEN RAISE EXCEPTION 'logical opening not atomic or carried transcript'; END IF;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'daily') RETURNING session_id INTO s2;
 r:=public.create_mode_suggestion(u,s2,'coach'); id:=(r->>'offer_id')::UUID;
 PERFORM public.set_mode_suggestion_preference(u,FALSE);
 IF public.resolve_mode_suggestion(u,id,TRUE) IS NOT NULL THEN
 RAISE EXCEPTION 'disabled offer confirmed'; END IF;
 PERFORM public.set_mode_suggestion_preference(u,TRUE);
 IF public.create_mode_suggestion(u,s2,'coach') IS NOT NULL THEN
 RAISE EXCEPTION 'declined suppression lost'; END IF;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'daily') RETURNING session_id INTO s2;
 r:=public.create_mode_suggestion(u,s2,'coach'); id:=(r->>'offer_id')::UUID;
 UPDATE public.mode_suggestions SET expires_at=now()-interval '1 second' WHERE offer_id=id;
 IF public.resolve_mode_suggestion(u,id,TRUE) IS NOT NULL THEN
 RAISE EXCEPTION 'expired offer confirmed'; END IF;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'daily') RETURNING session_id INTO s2;
 r:=public.create_mode_suggestion(u,s2,'coach'); id:=(r->>'offer_id')::UUID;
 UPDATE public.mode_grants SET revoked_at=now() WHERE user_id=u;
 IF public.resolve_mode_suggestion(u,id,TRUE) IS NOT NULL THEN
 RAISE EXCEPTION 'revoked grant confirmed'; END IF;
 IF has_function_privilege('anon','public.create_mode_suggestion(uuid,uuid,text,boolean)','EXECUTE')
 OR has_function_privilege('authenticated','public.resolve_mode_suggestion(uuid,uuid,boolean)','EXECUTE')
 OR has_table_privilege('service_role','public.mode_suggestions','INSERT')
 OR has_table_privilege('service_role','public.mode_suggestions','SELECT')
 OR has_table_privilege('service_role','public.mode_suggestion_preferences','SELECT') THEN
 RAISE EXCEPTION 'untrusted mutation privileges'; END IF;
END $$;

-- Receipt fencing, latest Daily control, late guards, and transaction rollback.
DO $$ DECLARE u UUID; other UUID; src UUID; control UUID; fresh UUID; id UUID;
 r JSONB; retry JSONB; token UUID; target UUID; program UUID; BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91021101) RETURNING user_id INTO u;
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91021102) RETURNING user_id INTO other;
 PERFORM public.set_mode_suggestion_preference(u,TRUE);
 INSERT INTO public.mode_grants(user_id,mode_id,granted_by,reason,expires_at)
 VALUES(u,'coach','owner','fictional atomic probe',now()+interval '1 day');
 INSERT INTO public.sessions(user_id,mode_id,started_at) VALUES(u,'daily',now()-interval '1 second') RETURNING session_id INTO src;
 r:=public.create_mode_suggestion(u,src,'coach'); id:=(r->>'offer_id')::UUID;
 INSERT INTO public.sessions(user_id,mode_id,started_at) VALUES(u,'daily',clock_timestamp()) RETURNING session_id INTO control;
 r:=public.resolve_mode_suggestion(u,id,TRUE); token:=(r->>'opening_claim_token')::UUID;
 target:=(r->>'opened_session_id')::UUID;
 IF (r->>'control_session_id')::UUID IS DISTINCT FROM control OR
 (SELECT count(*) FROM public.sessions WHERE session_id IN(src,control) AND active_mode_id='coach')<>2
 THEN RAISE EXCEPTION 'latest Daily not atomically selected'; END IF;
 IF public.claim_mode_suggestion_opening(u,id)->>'status'<>'busy'
 OR public.release_mode_suggestion_opening(other,id,token)
 OR public.complete_mode_suggestion_opening(u,id,gen_random_uuid())
 THEN RAISE EXCEPTION 'opening claim ownership/lease failure'; END IF;
 UPDATE public.mode_suggestions SET opening_claimed_at=clock_timestamp()-interval '6 minutes' WHERE offer_id=id;
 IF public.complete_mode_suggestion_opening(u,id,token) THEN RAISE EXCEPTION 'expired claim completed'; END IF;
 retry:=public.claim_mode_suggestion_opening(u,id);
 IF retry->>'status'<>'claimed' OR (retry->'offer'->>'opened_session_id')::UUID<>target
 OR (retry->'offer'->>'opening_claim_token')::UUID=token THEN RAISE EXCEPTION 'retry replaced target or failed fencing'; END IF;
 token:=(retry->'offer'->>'opening_claim_token')::UUID;
 IF NOT public.release_mode_suggestion_opening(u,id,token) THEN RAISE EXCEPTION 'release failed'; END IF;
 INSERT INTO public.sessions(user_id,mode_id,started_at) VALUES(u,'daily',clock_timestamp()) RETURNING session_id INTO fresh;
 IF public.claim_mode_suggestion_opening(u,id) IS NOT NULL OR
 (SELECT active_mode_id FROM public.sessions WHERE session_id=fresh) IS NOT NULL
 THEN RAISE EXCEPTION 'old receipt overrides newer Daily'; END IF;
 -- A Handoff that appeared after offer creation blocks confirmation and leaves no new target.
 r:=public.create_mode_suggestion(u,fresh,'recommender',FALSE); id:=(r->>'offer_id')::UUID;
 INSERT INTO public.mode_handoffs(user_id,session_id,source_mode_id,target_mode_id,source_grant_required,target_grant_required,carried_request,expires_at)
 VALUES(u,fresh,'daily','coach',FALSE,TRUE,'fictional guard',now()+interval '5 minutes');
 IF public.resolve_mode_suggestion(u,id,TRUE) IS NOT NULL OR EXISTS(
 SELECT 1 FROM public.sessions WHERE user_id=u AND mode_id='recommender') THEN RAISE EXCEPTION 'late Handoff not guarded'; END IF;
 UPDATE public.mode_handoffs SET resolved_at=now(),resolution='declined' WHERE user_id=u;
 INSERT INTO public.sessions(user_id,mode_id,started_at) VALUES(u,'daily',clock_timestamp()) RETURNING session_id INTO fresh;
 r:=public.create_mode_suggestion(u,fresh,'recommender',FALSE); id:=(r->>'offer_id')::UUID;
 INSERT INTO public.coaching_programs(user_id,goal,success_measure,check_in_days,check_in_time,timezone,state)
 VALUES(u,'fictional reading','one page',ARRAY[1],'09:00','UTC','draft') RETURNING program_id INTO program;
 PERFORM public.issue_coaching_approval(u,program,1);
 IF public.resolve_mode_suggestion(u,id,TRUE) IS NOT NULL THEN RAISE EXCEPTION 'late Coach approval not guarded'; END IF;
 UPDATE public.coaching_approvals SET used_at=now() WHERE user_id=u;
 IF EXISTS(SELECT 1 FROM public.messages WHERE session_id=target) THEN RAISE EXCEPTION 'carried transcript exists'; END IF;
 IF has_function_privilege('service_role','public.lock_owned_mode_suggestion(uuid,uuid)','EXECUTE')
 OR has_function_privilege('authenticated','public.claim_mode_suggestion_opening(uuid,uuid)','EXECUTE')
 OR NOT has_function_privilege('service_role','public.complete_mode_suggestion_opening(uuid,uuid,uuid)','EXECUTE')
 THEN RAISE EXCEPTION 'opening RPC privileges'; END IF;
END $$;
CREATE FUNCTION pg_temp.reject_suggestion_target() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.mode_id='recommender' THEN RAISE EXCEPTION 'fictional_insert_failure'; END IF; RETURN NEW; END $$;
CREATE TRIGGER suggestion_atomic_probe BEFORE INSERT ON public.sessions FOR EACH ROW EXECUTE FUNCTION pg_temp.reject_suggestion_target();
DO $$ DECLARE u UUID; src UUID; id UUID; r JSONB; BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91021103) RETURNING user_id INTO u;
 PERFORM public.set_mode_suggestion_preference(u,TRUE);
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'daily') RETURNING session_id INTO src;
 r:=public.create_mode_suggestion(u,src,'recommender',FALSE); id:=(r->>'offer_id')::UUID;
 BEGIN
  PERFORM public.resolve_mode_suggestion(u,id,TRUE);
  RAISE EXCEPTION 'expected injected failure';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'fictional_insert_failure' THEN RAISE; END IF; END;
 IF public.get_mode_suggestion(u,id)->>'state'<>'pending' OR
 (SELECT active_mode_id FROM public.sessions WHERE session_id=src) IS NOT NULL OR
 EXISTS(SELECT 1 FROM public.sessions WHERE user_id=u AND mode_id='recommender')
 THEN RAISE EXCEPTION 'partial logical opening survived rollback'; END IF;
END $$;
DROP TRIGGER suggestion_atomic_probe ON public.sessions;
ROLLBACK;
