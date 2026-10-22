\set ON_ERROR_STOP on
BEGIN;
DO $$ DECLARE u UUID; outsider UUID; s UUID; s2 UUID; r JSONB; id UUID; BEGIN
 IF public.get_app_schema_version()<>21 THEN RAISE EXCEPTION '021 not reported'; END IF;
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91021001) RETURNING user_id INTO u;
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(91021002) RETURNING user_id INTO outsider;
 INSERT INTO public.sessions(user_id,mode_id) VALUES(u,'daily') RETURNING session_id INTO s;
 IF public.create_mode_suggestion(u,s,'coach') IS NOT NULL THEN
 RAISE EXCEPTION 'ungranted offer admitted'; END IF;
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
 IF public.resolve_mode_suggestion(u,id,TRUE)->>'state'<>'confirmed' THEN
 RAISE EXCEPTION 'confirmation failed'; END IF;
 IF public.resolve_mode_suggestion(u,id,TRUE) IS NOT NULL THEN
 RAISE EXCEPTION 'double confirmation accepted'; END IF;
 IF EXISTS(SELECT 1 FROM public.sessions WHERE user_id=u AND mode_id='coach') THEN
 RAISE EXCEPTION 'Store executed target'; END IF;
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
 OR has_table_privilege('service_role','public.mode_suggestions','INSERT') THEN
 RAISE EXCEPTION 'untrusted mutation privileges'; END IF;
END $$;
ROLLBACK;
