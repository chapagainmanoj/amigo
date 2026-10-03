-- PROPOSAL ONLY. Requires separate owner approval; do not copy into migrations yet.
-- Migration 015 remains separately parked. Adoption requires 015 first, then this 016.
BEGIN;

DO $$
BEGIN
  IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 15) <> 15
     OR (SELECT max(version) FROM public.schema_migrations) <> 15 THEN
    RAISE EXCEPTION '016 requires the complete approved 001-015 chain';
  END IF;
END;
$$;

ALTER TABLE public.sessions ADD COLUMN active_mode_id TEXT
  CHECK (active_mode_id IS NULL OR active_mode_id ~ '^[a-z][a-z0-9_]{0,31}$');
ALTER TABLE public.sessions ADD CONSTRAINT sessions_owned_identity UNIQUE (session_id, user_id);

CREATE TABLE public.mode_grants (
  grant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.user_profiles(user_id),
  mode_id TEXT NOT NULL CHECK (mode_id ~ '^[a-z][a-z0-9_]{0,31}$' AND mode_id <> 'daily'),
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  revoked_at TIMESTAMPTZ,
  granted_by TEXT NOT NULL CHECK (btrim(granted_by) <> ''),
  reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
  CHECK (expires_at > granted_at AND expires_at <= granted_at + interval '14 days'),
  CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
  UNIQUE (grant_id, user_id, mode_id)
);
-- Expired rows are closed/audited inside grant_mode before replacement; dynamic now() cannot
-- appear in a partial unique-index predicate.
CREATE UNIQUE INDEX mode_grants_one_open_per_participant
  ON public.mode_grants(user_id, mode_id) WHERE revoked_at IS NULL;
CREATE INDEX mode_grants_capacity ON public.mode_grants(mode_id, expires_at)
  WHERE revoked_at IS NULL;

CREATE TABLE public.mode_grant_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  grant_id UUID NOT NULL,
  user_id UUID NOT NULL,
  mode_id TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('granted', 'revoked', 'expired')),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  operator TEXT NOT NULL CHECK (btrim(operator) <> ''),
  reason TEXT NOT NULL CHECK (btrim(reason) <> ''),
  FOREIGN KEY (grant_id, user_id, mode_id)
    REFERENCES public.mode_grants(grant_id, user_id, mode_id)
);

CREATE TABLE public.mode_handoffs (
  handoff_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.user_profiles(user_id),
  session_id UUID NOT NULL,
  source_mode_id TEXT NOT NULL CHECK (source_mode_id ~ '^[a-z][a-z0-9_]{0,31}$'),
  target_mode_id TEXT NOT NULL CHECK (target_mode_id ~ '^[a-z][a-z0-9_]{0,31}$'),
  source_grant_required BOOLEAN NOT NULL,
  target_grant_required BOOLEAN NOT NULL,
  carried_request TEXT NOT NULL CHECK (btrim(carried_request) <> ''),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  resolved_at TIMESTAMPTZ,
  resolution TEXT CHECK (resolution IN ('confirmed', 'declined', 'expired', 'unavailable')),
  CHECK (source_mode_id <> target_mode_id),
  CHECK (expires_at > created_at AND expires_at <= created_at + interval '10 minutes'),
  CHECK ((resolved_at IS NULL) = (resolution IS NULL)),
  FOREIGN KEY (session_id, user_id) REFERENCES public.sessions(session_id, user_id)
);
CREATE INDEX mode_handoffs_pending ON public.mode_handoffs(user_id, session_id, expires_at)
  WHERE resolved_at IS NULL;

ALTER TABLE public.mode_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mode_grant_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mode_handoffs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.mode_grants, public.mode_grant_events, public.mode_handoffs
  FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.mode_grants, public.mode_grant_events, public.mode_handoffs
  TO authenticated, service_role;

CREATE POLICY mode_grant_select_own ON public.mode_grants FOR SELECT TO authenticated
  USING (user_id = (SELECT user_id FROM public.user_profiles WHERE supabase_auth_id = auth.uid()));
CREATE POLICY mode_grant_event_select_own ON public.mode_grant_events FOR SELECT TO authenticated
  USING (user_id = (SELECT user_id FROM public.user_profiles WHERE supabase_auth_id = auth.uid()));
CREATE POLICY mode_handoff_select_own ON public.mode_handoffs FOR SELECT TO authenticated
  USING (user_id = (SELECT user_id FROM public.user_profiles WHERE supabase_auth_id = auth.uid()));

CREATE FUNCTION public.grant_mode(
  p_user_id UUID, p_mode_id TEXT, p_operator TEXT, p_reason TEXT,
  p_expires_at TIMESTAMPTZ DEFAULT now() + interval '14 days'
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_now TIMESTAMPTZ;
  v_grant public.mode_grants%ROWTYPE;
  v_expired public.mode_grants%ROWTYPE;
BEGIN
  v_now := clock_timestamp();
  IF p_mode_id IS NULL OR p_mode_id = 'daily'
     OR p_mode_id !~ '^[a-z][a-z0-9_]{0,31}$'
     OR p_operator IS NULL OR btrim(p_operator) = ''
     OR p_reason IS NULL OR btrim(p_reason) = ''
     OR p_expires_at IS NULL OR p_expires_at <= v_now
     OR p_expires_at > v_now + interval '14 days' THEN
    RETURN jsonb_build_object('status', 'invalid');
  END IF;
  -- Every grant/revoke/confirm operation shares this per-Mode capacity lock.
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-mode:' || p_mode_id, 0));
  -- Acquire the INSERT's parent-key protection before its last expiry check. An unlocked
  -- existence read would leave the foreign-key check able to wait past p_expires_at.
  -- Lock order is Mode advisory lock -> owned profile key-share -> grant rows. No Mode RPC
  -- acquires a Mode lock while already holding a profile lock, and this RPC never locks Sessions.
  PERFORM 1 FROM public.user_profiles WHERE user_id = p_user_id FOR KEY SHARE;
  IF NOT FOUND THEN RETURN jsonb_build_object('status', 'invalid'); END IF;
  v_now := clock_timestamp();
  IF p_expires_at <= v_now THEN RETURN jsonb_build_object('status', 'invalid'); END IF;
  FOR v_expired IN
    UPDATE public.mode_grants SET revoked_at = v_now
    WHERE mode_id = p_mode_id AND revoked_at IS NULL AND expires_at <= v_now RETURNING *
  LOOP
    INSERT INTO public.mode_grant_events(grant_id, user_id, mode_id, action, operator, reason)
    VALUES (v_expired.grant_id, v_expired.user_id, p_mode_id, 'expired', p_operator,
            'Expiry observed while granting: ' || p_reason);
  END LOOP;
  SELECT * INTO v_grant FROM public.mode_grants
    WHERE user_id = p_user_id AND mode_id = p_mode_id AND revoked_at IS NULL;
  IF FOUND THEN
    RETURN jsonb_build_object('status', 'already_active', 'grant', to_jsonb(v_grant));
  END IF;
  IF (SELECT count(*) FROM public.mode_grants
      WHERE mode_id = p_mode_id AND revoked_at IS NULL AND expires_at > v_now) >= 5 THEN
    RETURN jsonb_build_object('status', 'cap_reached');
  END IF;
  INSERT INTO public.mode_grants(user_id, mode_id, granted_at, expires_at, granted_by, reason)
    VALUES (p_user_id, p_mode_id, v_now, p_expires_at, p_operator, p_reason) RETURNING * INTO v_grant;
  INSERT INTO public.mode_grant_events(grant_id, user_id, mode_id, action, operator, reason)
    VALUES (v_grant.grant_id, p_user_id, p_mode_id, 'granted', p_operator, p_reason);
  RETURN jsonb_build_object('status', 'granted', 'grant', to_jsonb(v_grant));
END;
$$;

CREATE FUNCTION public.revoke_mode_grant(
  p_user_id UUID, p_mode_id TEXT, p_operator TEXT, p_reason TEXT
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_grant public.mode_grants%ROWTYPE;
BEGIN
  IF p_operator IS NULL OR btrim(p_operator) = '' OR p_reason IS NULL OR btrim(p_reason) = '' THEN
    RETURN jsonb_build_object('status', 'invalid');
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-mode:' || p_mode_id, 0));
  UPDATE public.mode_grants SET revoked_at = clock_timestamp()
    WHERE user_id = p_user_id AND mode_id = p_mode_id AND revoked_at IS NULL
    RETURNING * INTO v_grant;
  IF NOT FOUND THEN RETURN jsonb_build_object('status', 'not_active'); END IF;
  INSERT INTO public.mode_grant_events(grant_id, user_id, mode_id, action, operator, reason)
    VALUES (v_grant.grant_id, p_user_id, p_mode_id, 'revoked', p_operator, p_reason);
  RETURN jsonb_build_object('status', 'revoked', 'grant', to_jsonb(v_grant));
END;
$$;

CREATE FUNCTION public.set_active_mode(
  p_user_id UUID, p_session_id UUID, p_mode_id TEXT, p_grant_required BOOLEAN DEFAULT TRUE
)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_session public.sessions%ROWTYPE;
BEGIN
  -- The service derives grant_required from the authorized registry, never from model arguments.
  IF p_grant_required IS NULL THEN RETURN jsonb_build_object('status', 'invalid'); END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('amigo-mode:' || coalesce(p_mode_id, 'daily'), 0));
  SELECT * INTO v_session FROM public.sessions
    WHERE user_id = p_user_id AND session_id = p_session_id AND ended_at IS NULL FOR UPDATE;
  IF NOT FOUND THEN RETURN jsonb_build_object('status', 'unavailable'); END IF;
  IF coalesce(p_mode_id, 'daily') <> 'daily' AND p_grant_required AND NOT EXISTS (
    SELECT 1 FROM public.mode_grants WHERE user_id = p_user_id AND mode_id = p_mode_id
      AND revoked_at IS NULL AND expires_at > clock_timestamp()) THEN
    RETURN jsonb_build_object('status', 'unavailable');
  END IF;
  UPDATE public.sessions SET active_mode_id = NULLIF(p_mode_id, 'daily')
    WHERE user_id = p_user_id AND session_id = p_session_id AND ended_at IS NULL;
  IF NOT FOUND THEN RETURN jsonb_build_object('status', 'unavailable'); END IF;
  RETURN jsonb_build_object('status', 'set');
END;
$$;

CREATE FUNCTION public.create_mode_handoff(
  p_user_id UUID, p_session_id UUID, p_source_mode_id TEXT, p_target_mode_id TEXT,
  p_carried_request TEXT, p_source_grant_required BOOLEAN DEFAULT TRUE,
  p_target_grant_required BOOLEAN DEFAULT TRUE
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_mode TEXT;
  v_session public.sessions%ROWTYPE;
  v_handoff public.mode_handoffs%ROWTYPE;
  v_now TIMESTAMPTZ;
BEGIN
  IF p_source_mode_id IS NULL OR p_target_mode_id IS NULL
     OR p_source_mode_id !~ '^[a-z][a-z0-9_]{0,31}$'
     OR p_target_mode_id !~ '^[a-z][a-z0-9_]{0,31}$'
     OR p_source_mode_id = p_target_mode_id
     OR p_source_grant_required IS NULL OR p_target_grant_required IS NULL
     OR p_carried_request IS NULL OR btrim(p_carried_request) = '' THEN
    RETURN jsonb_build_object('status', 'invalid');
  END IF;
  -- Lock all involved Mode capacities in a total order, then Session, then handoff.
  FOR v_mode IN SELECT DISTINCT mode_id FROM unnest(ARRAY[p_source_mode_id, p_target_mode_id])
    AS modes(mode_id) ORDER BY mode_id
  LOOP
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-mode:' || v_mode, 0));
  END LOOP;
  SELECT * INTO v_session FROM public.sessions
    WHERE session_id = p_session_id AND user_id = p_user_id AND ended_at IS NULL FOR UPDATE;
  IF NOT FOUND OR coalesce(v_session.active_mode_id, 'daily') <> p_source_mode_id THEN
    RETURN jsonb_build_object('status', 'unavailable');
  END IF;
  v_now := clock_timestamp();
  IF EXISTS (SELECT 1 FROM unnest(ARRAY[p_source_mode_id, p_target_mode_id],
    ARRAY[p_source_grant_required, p_target_grant_required]) AS modes(mode_id, grant_required)
    WHERE mode_id <> 'daily' AND grant_required AND NOT EXISTS (SELECT 1 FROM public.mode_grants AS grant_record
      WHERE grant_record.user_id = p_user_id AND grant_record.mode_id = modes.mode_id
        AND grant_record.revoked_at IS NULL AND grant_record.expires_at > v_now)) THEN
    RETURN jsonb_build_object('status', 'unavailable');
  END IF;
  -- Registry-declared targets are checked by the authorized Handoffs Tool before this RPC.
  INSERT INTO public.mode_handoffs(user_id, session_id, source_mode_id, target_mode_id,
                                  source_grant_required, target_grant_required,
                                  carried_request, created_at, expires_at)
    VALUES (p_user_id, p_session_id, p_source_mode_id, p_target_mode_id,
            p_source_grant_required, p_target_grant_required,
            p_carried_request, v_now, v_now + interval '10 minutes') RETURNING * INTO v_handoff;
  RETURN jsonb_build_object('status', 'pending', 'handoff', to_jsonb(v_handoff));
END;
$$;

CREATE FUNCTION public.resolve_mode_handoff(
  p_user_id UUID, p_session_id UUID, p_handoff_id UUID, p_confirm BOOLEAN
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_mode TEXT;
  v_handoff public.mode_handoffs%ROWTYPE;
  v_session public.sessions%ROWTYPE;
  v_resolution TEXT;
  v_now TIMESTAMPTZ;
BEGIN
  IF p_confirm IS NULL THEN RETURN jsonb_build_object('status', 'invalid'); END IF;
  SELECT * INTO v_handoff FROM public.mode_handoffs
    WHERE handoff_id = p_handoff_id AND user_id = p_user_id AND session_id = p_session_id;
  IF NOT FOUND THEN RETURN jsonb_build_object('status', 'unavailable'); END IF;
  FOR v_mode IN SELECT DISTINCT mode_id FROM unnest(
    ARRAY[v_handoff.source_mode_id, v_handoff.target_mode_id]) AS modes(mode_id) ORDER BY mode_id
  LOOP
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-mode:' || v_mode, 0));
  END LOOP;
  SELECT * INTO v_session FROM public.sessions
    WHERE session_id = p_session_id AND user_id = p_user_id FOR UPDATE;
  SELECT * INTO v_handoff FROM public.mode_handoffs
    WHERE handoff_id = p_handoff_id AND user_id = p_user_id AND session_id = p_session_id FOR UPDATE;
  IF NOT FOUND OR v_handoff.resolved_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'unavailable');
  END IF;
  v_now := clock_timestamp();
  v_resolution := CASE
    WHEN v_handoff.expires_at <= v_now THEN 'expired'
    WHEN NOT p_confirm THEN 'declined'
    WHEN v_session.ended_at IS NOT NULL
      OR coalesce(v_session.active_mode_id, 'daily') <> v_handoff.source_mode_id
      OR EXISTS (SELECT 1 FROM unnest(ARRAY[v_handoff.source_mode_id, v_handoff.target_mode_id],
         ARRAY[v_handoff.source_grant_required, v_handoff.target_grant_required])
         AS modes(mode_id, grant_required) WHERE mode_id <> 'daily' AND grant_required
         AND NOT EXISTS (SELECT 1 FROM public.mode_grants AS grant_record
           WHERE grant_record.user_id = p_user_id AND grant_record.mode_id = modes.mode_id
             AND grant_record.revoked_at IS NULL AND grant_record.expires_at > v_now))
      THEN 'unavailable'
    ELSE 'confirmed' END;
  UPDATE public.mode_handoffs SET resolved_at = v_now, resolution = v_resolution
    WHERE handoff_id = p_handoff_id RETURNING * INTO v_handoff;
  IF v_resolution = 'confirmed' THEN
    UPDATE public.sessions SET active_mode_id = NULLIF(v_handoff.target_mode_id, 'daily')
      WHERE session_id = p_session_id AND user_id = p_user_id;
    RETURN jsonb_build_object('status', 'confirmed', 'handoff', to_jsonb(v_handoff));
  END IF;
  RETURN jsonb_build_object('status', v_resolution);
END;
$$;

REVOKE ALL ON FUNCTION public.grant_mode(UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ),
  public.revoke_mode_grant(UUID, TEXT, TEXT, TEXT), public.set_active_mode(UUID, UUID, TEXT, BOOLEAN),
  public.create_mode_handoff(UUID, UUID, TEXT, TEXT, TEXT, BOOLEAN, BOOLEAN),
  public.resolve_mode_handoff(UUID, UUID, UUID, BOOLEAN) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.grant_mode(UUID, TEXT, TEXT, TEXT, TIMESTAMPTZ),
  public.revoke_mode_grant(UUID, TEXT, TEXT, TEXT), public.set_active_mode(UUID, UUID, TEXT, BOOLEAN),
  public.create_mode_handoff(UUID, UUID, TEXT, TEXT, TEXT, BOOLEAN, BOOLEAN),
  public.resolve_mode_handoff(UUID, UUID, UUID, BOOLEAN) TO service_role;

-- Earn 016 through the objects/constraints it creates before recording its ledger revision.
DO $$
BEGIN
  IF to_regclass('public.mode_grants') IS NULL OR to_regclass('public.mode_grant_events') IS NULL
     OR to_regclass('public.mode_handoffs') IS NULL
     OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute
       WHERE attrelid = 'public.sessions'::regclass AND attname = 'active_mode_id' AND NOT attisdropped)
  THEN RAISE EXCEPTION '016 objects were not created'; END IF;
  INSERT INTO public.schema_migrations(version) VALUES (16);
END;
$$;
COMMIT;
