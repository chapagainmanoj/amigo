BEGIN;
DO $$ BEGIN
 IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 20) <> 20
 OR (SELECT max(version) FROM public.schema_migrations) <> 20 THEN
 RAISE EXCEPTION '021 requires the complete approved 001-020 chain'; END IF;
END $$;
CREATE TABLE public.mode_suggestion_preferences (
 user_id UUID PRIMARY KEY REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 enabled BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE public.mode_suggestions (
 offer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 source_session_id UUID NOT NULL,
 target_mode_id TEXT NOT NULL CHECK(target_mode_id IN ('coach','reflect','recommender')),
 grant_required BOOLEAN NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','confirmed','declined','expired')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '10 minutes',
 opened_session_id UUID, control_session_id UUID, opening_claim_token UUID, opening_claimed_at TIMESTAMPTZ,
 opening_completed_at TIMESTAMPTZ,
 UNIQUE(user_id,source_session_id),
 FOREIGN KEY(source_session_id,user_id) REFERENCES public.sessions(session_id,user_id) ON DELETE CASCADE,
 FOREIGN KEY(control_session_id,user_id) REFERENCES public.sessions(session_id,user_id) ON DELETE CASCADE,
 FOREIGN KEY(opened_session_id,user_id) REFERENCES public.sessions(session_id,user_id) ON DELETE CASCADE,
 CHECK(state<>'confirmed' OR (opened_session_id IS NOT NULL AND control_session_id IS NOT NULL))

);
ALTER TABLE public.mode_suggestion_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mode_suggestions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.mode_suggestion_preferences,public.mode_suggestions
 FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION public.get_mode_suggestion_preference(p_user_id UUID) RETURNS BOOLEAN
LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT coalesce((SELECT enabled FROM public.mode_suggestion_preferences WHERE user_id=p_user_id),FALSE);
$$;
CREATE FUNCTION public.set_mode_suggestion_preference(p_user_id UUID,p_enabled BOOLEAN)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN
 IF p_enabled IS NULL THEN RAISE EXCEPTION 'invalid_suggestion_preference'; END IF;
 PERFORM 1 FROM public.user_profiles WHERE user_id=p_user_id FOR KEY SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'suggestion_owner_unavailable'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-suggestions:'||p_user_id,0));
 INSERT INTO public.mode_suggestion_preferences(user_id,enabled) VALUES(p_user_id,p_enabled)
 ON CONFLICT(user_id) DO UPDATE SET enabled=EXCLUDED.enabled;
 IF NOT p_enabled THEN UPDATE public.mode_suggestions SET state='declined'
 WHERE user_id=p_user_id AND state='pending'; END IF;
 RETURN p_enabled;
END $$;
CREATE FUNCTION public.create_mode_suggestion(p_user_id UUID,p_session_id UUID,
 p_target_mode_id TEXT,p_grant_required BOOLEAN DEFAULT TRUE)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.mode_suggestions%ROWTYPE; BEGIN
 IF p_target_mode_id IS NULL OR p_target_mode_id NOT IN ('coach','reflect','recommender')
 OR p_grant_required IS NULL THEN RAISE EXCEPTION 'invalid_suggestion_target'; END IF;
 PERFORM 1 FROM public.user_profiles WHERE user_id=p_user_id FOR KEY SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'suggestion_owner_unavailable'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-suggestions:'||p_user_id,0));
 PERFORM 1 FROM public.sessions WHERE session_id=p_session_id AND user_id=p_user_id
 AND mode_id='daily' AND ended_at IS NULL FOR KEY SHARE;
 IF NOT FOUND OR NOT public.get_mode_suggestion_preference(p_user_id)
 OR EXISTS(SELECT 1 FROM public.mode_handoffs WHERE user_id=p_user_id
 AND resolved_at IS NULL AND expires_at>clock_timestamp())
 OR EXISTS(SELECT 1 FROM public.coaching_approvals WHERE user_id=p_user_id
 AND used_at IS NULL AND expires_at>clock_timestamp())
 OR (p_grant_required AND NOT EXISTS(SELECT 1 FROM public.mode_grants
 WHERE user_id=p_user_id AND mode_id=p_target_mode_id AND revoked_at IS NULL
 AND expires_at>clock_timestamp())) THEN RETURN NULL; END IF;
 INSERT INTO public.mode_suggestions(user_id,source_session_id,target_mode_id,grant_required)
 VALUES(p_user_id,p_session_id,p_target_mode_id,p_grant_required)
 ON CONFLICT(user_id,source_session_id) DO NOTHING RETURNING * INTO r;
 IF NOT FOUND THEN RETURN NULL; END IF;
 RETURN to_jsonb(r);
END $$;
CREATE FUNCTION public.get_mode_suggestion(p_user_id UUID,p_offer_id UUID) RETURNS JSONB
LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT to_jsonb(r) FROM public.mode_suggestions r WHERE user_id=p_user_id AND offer_id=p_offer_id;
$$;
-- Private helpers share a single lock order; only the service RPCs below are executable.
CREATE FUNCTION public.lock_owned_mode_suggestion(p_user_id UUID,p_offer_id UUID)
RETURNS public.mode_suggestions LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.mode_suggestions; source_id UUID; control_id UUID; bound_control_id UUID; target_id UUID; BEGIN
 PERFORM 1 FROM public.user_profiles WHERE user_id=p_user_id FOR KEY SHARE;
 IF NOT FOUND THEN RETURN NULL; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('amigo-suggestions:'||p_user_id,0));
 SELECT source_session_id,control_session_id,opened_session_id INTO source_id,bound_control_id,target_id FROM public.mode_suggestions
 WHERE user_id=p_user_id AND offer_id=p_offer_id;
 IF NOT FOUND THEN RETURN NULL; END IF;
 -- Session before offer prevents cascade deletion from reversing the row-lock order.
 SELECT session_id INTO control_id FROM public.sessions WHERE user_id=p_user_id
 AND mode_id='daily' AND ended_at IS NULL ORDER BY started_at DESC,session_id DESC LIMIT 1;
 -- Every Session referenced by a cascading FK precedes the receipt row; deterministic order
 -- also covers a target/control deletion while a confirmed opening is being reclaimed.
 PERFORM 1 FROM public.sessions WHERE user_id=p_user_id AND session_id IN (source_id,control_id,bound_control_id,target_id)
 ORDER BY session_id FOR UPDATE;
 IF NOT EXISTS(SELECT 1 FROM public.sessions WHERE user_id=p_user_id AND session_id=source_id)
 THEN RETURN NULL; END IF;
 SELECT * INTO r FROM public.mode_suggestions WHERE user_id=p_user_id AND offer_id=p_offer_id FOR UPDATE;
 RETURN r;
END $$;
CREATE FUNCTION public.mode_suggestion_confirmation_blocked(p_user_id UUID) RETURNS BOOLEAN
LANGUAGE SQL STABLE SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.mode_handoffs WHERE user_id=p_user_id
   AND resolved_at IS NULL AND expires_at>clock_timestamp())
 OR EXISTS(SELECT 1 FROM public.coaching_approvals WHERE user_id=p_user_id
   AND used_at IS NULL AND expires_at>clock_timestamp());
$$;
CREATE FUNCTION public.mode_suggestion_opening_allowed(r public.mode_suggestions) RETURNS BOOLEAN
LANGUAGE plpgsql SET search_path='' AS $$
DECLARE control_row public.sessions; BEGIN
 IF NOT public.get_mode_suggestion_preference(r.user_id) THEN RETURN FALSE; END IF;
 -- Approval issuance locks its Program, so existing pending approvals cannot race this read.
 PERFORM 1 FROM public.coaching_programs WHERE user_id=r.user_id AND state NOT IN ('completed','stopped') FOR UPDATE;
 IF public.mode_suggestion_confirmation_blocked(r.user_id) THEN RETURN FALSE; END IF;
 IF r.grant_required THEN
   PERFORM 1 FROM public.mode_grants WHERE user_id=r.user_id AND mode_id=r.target_mode_id
   AND revoked_at IS NULL AND expires_at>clock_timestamp() FOR SHARE;
   IF NOT FOUND THEN RETURN FALSE; END IF;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM public.sessions WHERE session_id=r.source_session_id AND user_id=r.user_id
   AND mode_id='daily' AND ended_at IS NULL AND coalesce(active_mode_id,'daily')=
   CASE WHEN r.state='confirmed' THEN r.target_mode_id ELSE 'daily' END) THEN RETURN FALSE; END IF;
 SELECT * INTO control_row FROM public.sessions WHERE user_id=r.user_id AND mode_id='daily'
 AND ended_at IS NULL ORDER BY started_at DESC,session_id DESC LIMIT 1;
 IF control_row.session_id IS NULL OR coalesce(control_row.active_mode_id,'daily')<>
 (CASE WHEN r.state='confirmed' THEN r.target_mode_id ELSE 'daily' END) THEN RETURN FALSE; END IF;
 IF r.state='confirmed' AND control_row.session_id IS DISTINCT FROM r.control_session_id THEN RETURN FALSE; END IF;
 IF r.state='confirmed' THEN
   PERFORM 1 FROM public.sessions WHERE user_id=r.user_id AND session_id=r.opened_session_id
   AND mode_id=r.target_mode_id AND active_mode_id=r.target_mode_id AND ended_at IS NULL FOR KEY SHARE;
   IF NOT FOUND THEN RETURN FALSE; END IF;
 END IF;
 RETURN TRUE;
END $$;
CREATE FUNCTION public.resolve_mode_suggestion(p_user_id UUID,p_offer_id UUID,p_confirm BOOLEAN)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.mode_suggestions; target public.sessions; tz TEXT; timeout_minutes INT;
 instant TIMESTAMPTZ; control_id UUID; BEGIN
 IF p_confirm IS NULL THEN RETURN NULL; END IF;
 r:=public.lock_owned_mode_suggestion(p_user_id,p_offer_id);
 IF r.offer_id IS NULL OR r.state<>'pending' THEN RETURN NULL; END IF;
 IF r.expires_at<=clock_timestamp() THEN
   UPDATE public.mode_suggestions SET state='expired' WHERE offer_id=r.offer_id; RETURN NULL; END IF;
 IF NOT p_confirm THEN
   UPDATE public.mode_suggestions SET state='declined' WHERE offer_id=r.offer_id RETURNING * INTO r;
   RETURN to_jsonb(r);
 END IF;
 IF NOT public.mode_suggestion_opening_allowed(r) THEN
   UPDATE public.mode_suggestions SET state='declined' WHERE offer_id=r.offer_id; RETURN NULL; END IF;
 instant:=clock_timestamp();
 SELECT coalesce(timezone,'UTC'),coalesce(session_timeout_minutes,120) INTO tz,timeout_minutes
 FROM public.user_profiles WHERE user_id=p_user_id;
 SELECT * INTO target FROM public.sessions WHERE user_id=p_user_id AND mode_id=r.target_mode_id
 AND ended_at IS NULL ORDER BY started_at DESC,session_id DESC LIMIT 1 FOR UPDATE;
 IF target.session_id IS NOT NULL AND (
   target.last_activity_at < instant-make_interval(mins=>timeout_minutes)
   OR (target.last_activity_at AT TIME ZONE tz)::DATE < (instant AT TIME ZONE tz)::DATE
 ) THEN
   UPDATE public.sessions SET ended_at=instant WHERE session_id=target.session_id;
   target.session_id:=NULL;
 END IF;
 IF target.session_id IS NULL THEN
   INSERT INTO public.sessions(user_id,session_type,mode_id,active_mode_id)
   VALUES(p_user_id,'casual',r.target_mode_id,r.target_mode_id) RETURNING * INTO target;
 ELSE
   UPDATE public.sessions SET active_mode_id=r.target_mode_id,last_activity_at=instant
   WHERE session_id=target.session_id RETURNING * INTO target;
 END IF;
 SELECT session_id INTO control_id FROM public.sessions WHERE user_id=p_user_id AND mode_id='daily'
 AND ended_at IS NULL ORDER BY started_at DESC,session_id DESC LIMIT 1 FOR UPDATE;
 UPDATE public.sessions SET active_mode_id=r.target_mode_id
 WHERE session_id IN (r.source_session_id,control_id) AND user_id=p_user_id;
 UPDATE public.mode_suggestions SET state='confirmed',opened_session_id=target.session_id,control_session_id=control_id,
 opening_claim_token=gen_random_uuid(),opening_claimed_at=clock_timestamp()
 WHERE offer_id=r.offer_id RETURNING * INTO r;
 RETURN to_jsonb(r);
END $$;
CREATE FUNCTION public.claim_mode_suggestion_opening(p_user_id UUID,p_offer_id UUID)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.mode_suggestions; BEGIN
 r:=public.lock_owned_mode_suggestion(p_user_id,p_offer_id);
 IF r.offer_id IS NULL OR r.state<>'confirmed' OR r.opening_completed_at IS NOT NULL THEN RETURN NULL; END IF;
 IF NOT public.mode_suggestion_opening_allowed(r) THEN RETURN NULL; END IF;
 IF r.opening_claimed_at>clock_timestamp()-interval '5 minutes' THEN
   RETURN jsonb_build_object('status','busy'); END IF;
 UPDATE public.mode_suggestions SET opening_claim_token=gen_random_uuid(),opening_claimed_at=clock_timestamp()
 WHERE offer_id=r.offer_id RETURNING * INTO r;
 RETURN jsonb_build_object('status','claimed','offer',to_jsonb(r));
END $$;
CREATE FUNCTION public.release_mode_suggestion_opening(p_user_id UUID,p_offer_id UUID,p_claim_token UUID)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.mode_suggestions; BEGIN
 r:=public.lock_owned_mode_suggestion(p_user_id,p_offer_id);
 IF r.offer_id IS NULL OR r.state<>'confirmed' OR r.opening_completed_at IS NOT NULL
 OR r.opening_claim_token IS DISTINCT FROM p_claim_token OR p_claim_token IS NULL
 OR r.opening_claimed_at<=clock_timestamp()-interval '5 minutes' THEN RETURN FALSE; END IF;
 UPDATE public.mode_suggestions SET opening_claim_token=NULL,opening_claimed_at=NULL WHERE offer_id=r.offer_id;
 RETURN TRUE;
END $$;
CREATE FUNCTION public.complete_mode_suggestion_opening(p_user_id UUID,p_offer_id UUID,p_claim_token UUID)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.mode_suggestions; BEGIN
 r:=public.lock_owned_mode_suggestion(p_user_id,p_offer_id);
 IF r.offer_id IS NULL OR r.state<>'confirmed' OR r.opening_completed_at IS NOT NULL
 OR r.opening_claim_token IS DISTINCT FROM p_claim_token OR p_claim_token IS NULL
 OR r.opening_claimed_at<=clock_timestamp()-interval '5 minutes'
 OR NOT public.mode_suggestion_opening_allowed(r) THEN RETURN FALSE; END IF;
 UPDATE public.mode_suggestions SET opening_completed_at=clock_timestamp() WHERE offer_id=r.offer_id;
 RETURN TRUE;
END $$;
REVOKE ALL ON FUNCTION public.lock_owned_mode_suggestion(UUID,UUID),
 public.mode_suggestion_confirmation_blocked(UUID),public.mode_suggestion_opening_allowed(public.mode_suggestions)
 FROM PUBLIC,anon,authenticated,service_role;
DO $$ DECLARE fn RECORD; BEGIN
 FOR fn IN SELECT p.oid::regprocedure signature FROM pg_catalog.pg_proc p
 JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
 AND p.proname IN ('get_mode_suggestion_preference','set_mode_suggestion_preference',
 'create_mode_suggestion','get_mode_suggestion','resolve_mode_suggestion',
 'claim_mode_suggestion_opening','release_mode_suggestion_opening','complete_mode_suggestion_opening') LOOP
 EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated',fn.signature);
 EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',fn.signature);
 END LOOP;
END $$;
DO $$ BEGIN
 IF to_regclass('public.mode_suggestions') IS NULL
 OR to_regprocedure('public.resolve_mode_suggestion(uuid,uuid,boolean)') IS NULL
 OR to_regprocedure('public.claim_mode_suggestion_opening(uuid,uuid)') IS NULL
 OR to_regprocedure('public.release_mode_suggestion_opening(uuid,uuid,uuid)') IS NULL
 OR to_regprocedure('public.complete_mode_suggestion_opening(uuid,uuid,uuid)') IS NULL
 OR NOT (SELECT relrowsecurity FROM pg_catalog.pg_class WHERE oid='public.mode_suggestions'::regclass)
 THEN RAISE EXCEPTION '021 objects were not created'; END IF;
 INSERT INTO public.schema_migrations(version) VALUES(21);
END $$;
COMMIT;
