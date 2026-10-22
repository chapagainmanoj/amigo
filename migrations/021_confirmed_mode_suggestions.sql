BEGIN;
DO $$ BEGIN
 IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 20) <> 20
 OR (SELECT max(version) FROM public.schema_migrations) <> 20 THEN
 RAISE EXCEPTION '021 requires the complete approved 001-020 chain'; END IF;
END $$;
CREATE TABLE public.mode_suggestion_preferences (
 user_id UUID PRIMARY KEY REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 enabled BOOLEAN NOT NULL
);
CREATE TABLE public.mode_suggestions (
 offer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 source_session_id UUID NOT NULL REFERENCES public.sessions(session_id) ON DELETE CASCADE,
 target_mode_id TEXT NOT NULL CHECK(target_mode_id IN ('coach','reflect','recommender')),
 grant_required BOOLEAN NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','confirmed','declined','expired')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '10 minutes',
 UNIQUE(user_id,source_session_id)
);
ALTER TABLE public.mode_suggestion_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mode_suggestions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.mode_suggestion_preferences,public.mode_suggestions
 FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.mode_suggestion_preferences,public.mode_suggestions TO service_role;
CREATE FUNCTION public.get_mode_suggestion_preference(p_user_id UUID) RETURNS BOOLEAN
LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT coalesce((SELECT enabled FROM public.mode_suggestion_preferences WHERE user_id=p_user_id),TRUE);
$$;
CREATE FUNCTION public.set_mode_suggestion_preference(p_user_id UUID,p_enabled BOOLEAN)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN
 IF p_enabled IS NULL THEN RAISE EXCEPTION 'invalid_suggestion_preference'; END IF;
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
CREATE FUNCTION public.resolve_mode_suggestion(p_user_id UUID,p_offer_id UUID,p_confirm BOOLEAN)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.mode_suggestions%ROWTYPE; BEGIN
 IF p_confirm IS NULL THEN RETURN NULL; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-suggestions:'||p_user_id,0));
 SELECT * INTO r FROM public.mode_suggestions WHERE user_id=p_user_id AND offer_id=p_offer_id FOR UPDATE;
 IF NOT FOUND OR r.state<>'pending' THEN RETURN NULL; END IF;
 IF r.expires_at<=clock_timestamp() THEN
 UPDATE public.mode_suggestions SET state='expired' WHERE offer_id=r.offer_id; RETURN NULL; END IF;
 IF NOT public.get_mode_suggestion_preference(p_user_id)
 OR NOT EXISTS(SELECT 1 FROM public.sessions WHERE session_id=r.source_session_id AND user_id=p_user_id
 AND ended_at IS NULL)
 OR (p_confirm AND r.grant_required AND NOT EXISTS(SELECT 1 FROM public.mode_grants
 WHERE user_id=p_user_id AND mode_id=r.target_mode_id AND revoked_at IS NULL
 AND expires_at>clock_timestamp())) THEN
 UPDATE public.mode_suggestions SET state='declined' WHERE offer_id=r.offer_id; RETURN NULL; END IF;
 UPDATE public.mode_suggestions SET state=CASE WHEN p_confirm THEN 'confirmed' ELSE 'declined' END
 WHERE offer_id=r.offer_id RETURNING * INTO r;
 RETURN to_jsonb(r);
END $$;
DO $$ DECLARE fn RECORD; BEGIN
 FOR fn IN SELECT p.oid::regprocedure signature FROM pg_catalog.pg_proc p
 JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public'
 AND p.proname IN ('get_mode_suggestion_preference','set_mode_suggestion_preference',
 'create_mode_suggestion','get_mode_suggestion','resolve_mode_suggestion') LOOP
 EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated',fn.signature);
 EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',fn.signature);
 END LOOP;
END $$;
DO $$ BEGIN
 IF to_regclass('public.mode_suggestions') IS NULL
 OR to_regprocedure('public.resolve_mode_suggestion(uuid,uuid,boolean)') IS NULL
 OR NOT (SELECT relrowsecurity FROM pg_catalog.pg_class WHERE oid='public.mode_suggestions'::regclass)
 THEN RAISE EXCEPTION '021 objects were not created'; END IF;
 INSERT INTO public.schema_migrations(version) VALUES(21);
END $$;
COMMIT;
