BEGIN;
DO $$ BEGIN
  IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 16) <> 16
     OR (SELECT max(version) FROM public.schema_migrations) <> 16 THEN
    RAISE EXCEPTION '017 requires the complete approved 001-016 chain';
  END IF;
END $$;

ALTER TABLE public.sessions ADD COLUMN mode_id TEXT NOT NULL DEFAULT 'daily'
  CHECK (mode_id ~ '^[a-z][a-z0-9_]{0,31}$');
UPDATE public.sessions SET mode_id = coalesce(active_mode_id, 'daily');
CREATE INDEX sessions_mode_open ON public.sessions(user_id, mode_id, ended_at);

-- One endpoint namespace enforces uniqueness across canonical endpoints AND aliases.
CREATE TABLE public.mode_conversation_endpoints (
  user_id UUID NOT NULL REFERENCES public.user_profiles(user_id),
  mode_id TEXT NOT NULL CHECK (mode_id ~ '^[a-z][a-z0-9_]{0,31}$'),
  channel TEXT NOT NULL CHECK (channel ~ '^[a-z][a-z0-9_]{0,31}$'),
  endpoint JSONB NOT NULL CHECK (jsonb_typeof(endpoint) = 'object' AND endpoint <> '{}'::jsonb),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at TIMESTAMPTZ,
  PRIMARY KEY (channel, endpoint),
  UNIQUE (user_id, mode_id, channel, endpoint)
);
CREATE TABLE public.mode_conversations (
  user_id UUID NOT NULL,
  mode_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  endpoint JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at TIMESTAMPTZ,
  PRIMARY KEY (user_id, mode_id, channel),
  UNIQUE (channel, endpoint),
  FOREIGN KEY (user_id, mode_id, channel, endpoint)
    REFERENCES public.mode_conversation_endpoints(user_id, mode_id, channel, endpoint)
);
ALTER TABLE public.mode_conversation_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mode_conversations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.mode_conversation_endpoints, public.mode_conversations
  FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON public.mode_conversation_endpoints, public.mode_conversations TO authenticated, service_role;
CREATE POLICY mode_conversation_endpoints_own ON public.mode_conversation_endpoints
  FOR SELECT TO authenticated USING (user_id = (
    SELECT user_id FROM public.user_profiles WHERE supabase_auth_id = auth.uid()));
CREATE POLICY mode_conversations_own ON public.mode_conversations
  FOR SELECT TO authenticated USING (user_id = (
    SELECT user_id FROM public.user_profiles WHERE supabase_auth_id = auth.uid()));

CREATE FUNCTION public.save_mode_conversation(
  p_user_id UUID, p_mode_id TEXT, p_channel TEXT, p_endpoint JSONB, p_alias BOOLEAN DEFAULT FALSE
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_endpoint public.mode_conversation_endpoints%ROWTYPE;
        v_canonical public.mode_conversations%ROWTYPE;
BEGIN
  IF p_mode_id IS NULL OR p_mode_id !~ '^[a-z][a-z0-9_]{0,31}$'
     OR p_channel IS NULL OR p_channel !~ '^[a-z][a-z0-9_]{0,31}$'
     OR p_endpoint IS NULL OR jsonb_typeof(p_endpoint) <> 'object' OR p_endpoint = '{}'::jsonb
     OR p_alias IS NULL THEN RAISE EXCEPTION 'invalid_mode_conversation'; END IF;
  -- A single namespace lock makes canonical replacement/alias registration atomic across tables.
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-conversations', 0));
  SELECT * INTO v_endpoint FROM public.mode_conversation_endpoints
    WHERE channel = p_channel AND endpoint = p_endpoint FOR UPDATE;
  IF FOUND AND (v_endpoint.user_id <> p_user_id OR v_endpoint.mode_id <> p_mode_id) THEN
    RAISE EXCEPTION 'conversation_endpoint_conflict';
  END IF;
  SELECT * INTO v_canonical FROM public.mode_conversations
    WHERE user_id=p_user_id AND mode_id=p_mode_id AND channel=p_channel;
  IF NOT p_alias AND FOUND AND v_canonical.closed_at IS NULL THEN
    RETURN to_jsonb(v_canonical);
  END IF;
  INSERT INTO public.mode_conversation_endpoints(user_id, mode_id, channel, endpoint)
    VALUES(p_user_id, p_mode_id, p_channel, p_endpoint)
    ON CONFLICT(channel, endpoint) DO UPDATE SET closed_at = NULL RETURNING * INTO v_endpoint;
  IF NOT p_alias THEN
    INSERT INTO public.mode_conversations(user_id, mode_id, channel, endpoint, created_at)
      VALUES(p_user_id, p_mode_id, p_channel, p_endpoint, v_endpoint.created_at)
      ON CONFLICT(user_id, mode_id, channel) DO UPDATE SET endpoint = EXCLUDED.endpoint,
        created_at = EXCLUDED.created_at, closed_at = NULL;
  ELSE
    INSERT INTO public.mode_conversations(user_id, mode_id, channel, endpoint, created_at)
      VALUES(p_user_id, p_mode_id, p_channel, p_endpoint, v_endpoint.created_at)
      ON CONFLICT(user_id, mode_id, channel) DO UPDATE SET closed_at =
        CASE WHEN public.mode_conversations.endpoint=EXCLUDED.endpoint THEN NULL
             ELSE public.mode_conversations.closed_at END;
  END IF;
  RETURN to_jsonb(v_endpoint);
END $$;
CREATE FUNCTION public.close_mode_conversation(p_user_id UUID, p_mode_id TEXT, p_channel TEXT)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$ BEGIN
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-conversations', 0));
  UPDATE public.mode_conversation_endpoints SET closed_at = clock_timestamp()
    WHERE user_id=p_user_id AND mode_id=p_mode_id AND channel=p_channel;
  UPDATE public.mode_conversations SET closed_at = clock_timestamp()
    WHERE user_id=p_user_id AND mode_id=p_mode_id AND channel=p_channel;
END $$;

ALTER TABLE public.mode_handoffs
  ADD COLUMN execution_claimed_at TIMESTAMPTZ,
  ADD COLUMN execution_claim_token UUID,
  ADD COLUMN execution_worker_id TEXT,
  ADD COLUMN execution_session_id UUID,
  ADD COLUMN execution_clock_at TIMESTAMPTZ,
  ADD COLUMN execution_attempts INT NOT NULL DEFAULT 0 CHECK (execution_attempts >= 0),
  ADD COLUMN executed_at TIMESTAMPTZ,
  ADD COLUMN execution_failed_at TIMESTAMPTZ,
  ADD COLUMN execution_user_message_id UUID,
  ADD COLUMN execution_assistant_message_id UUID,
  ADD COLUMN execution_failure_notice_at TIMESTAMPTZ,
  ADD COLUMN execution_failure_notice_outcome TEXT CHECK(execution_failure_notice_outcome IN
    ('attempted','endpoint_unavailable','owner_unavailable')),
  ADD COLUMN execution_failure_reason TEXT CHECK (execution_failure_reason IN
    ('session_unavailable','target_unavailable','execution_failed','attempts_exhausted')),
  ADD COLUMN execution_plan JSONB NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(execution_plan) = 'array' AND jsonb_array_length(execution_plan) <= 32),
  ADD FOREIGN KEY (execution_session_id, user_id) REFERENCES public.sessions(session_id, user_id);
CREATE INDEX mode_handoffs_execution_pending ON public.mode_handoffs(execution_claimed_at)
  WHERE resolution = 'confirmed' AND executed_at IS NULL AND execution_failed_at IS NULL;

CREATE FUNCTION public.claim_handoff_execution(
  p_user_id UUID, p_handoff_id UUID, p_worker_id TEXT, p_execution_session_id UUID DEFAULT NULL
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_handoff public.mode_handoffs%ROWTYPE; v_session public.sessions%ROWTYPE;
        v_session_id UUID; v_now TIMESTAMPTZ;
BEGIN
  IF p_worker_id IS NULL OR btrim(p_worker_id) = '' THEN
    RETURN jsonb_build_object('status', 'invalid'); END IF;
  SELECT * INTO v_handoff FROM public.mode_handoffs
    WHERE user_id=p_user_id AND handoff_id=p_handoff_id AND resolution='confirmed';
  IF NOT FOUND THEN RETURN jsonb_build_object('status', 'unavailable'); END IF;
  -- Same total order as 016: Mode capacity -> owned Session -> handoff.
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('amigo-mode:' || v_handoff.target_mode_id, 0));
  v_session_id := coalesce(v_handoff.execution_session_id, p_execution_session_id);
  SELECT * INTO v_session FROM public.sessions
    WHERE session_id=v_session_id AND user_id=p_user_id FOR UPDATE;
  SELECT * INTO v_handoff FROM public.mode_handoffs
    WHERE user_id=p_user_id AND handoff_id=p_handoff_id AND resolution='confirmed' FOR UPDATE;
  IF NOT FOUND THEN RETURN jsonb_build_object('status', 'unavailable'); END IF;
  IF v_handoff.executed_at IS NOT NULL THEN RETURN jsonb_build_object('status', 'executed'); END IF;
  IF v_handoff.execution_failed_at IS NOT NULL THEN
    RETURN jsonb_build_object('status', 'failed'); END IF;
  v_now := clock_timestamp();
  IF v_handoff.execution_claimed_at > v_now - interval '5 minutes' THEN
    RETURN jsonb_build_object('status', 'busy'); END IF;
  IF v_handoff.execution_attempts >= 2 THEN
    UPDATE public.mode_handoffs SET execution_failed_at=v_now,
      execution_failure_reason='attempts_exhausted' WHERE handoff_id=p_handoff_id;
    RETURN jsonb_build_object('status','unavailable','terminal',TRUE); END IF;
  IF v_session.session_id IS NULL
     OR (v_session.ended_at IS NOT NULL AND v_handoff.execution_session_id IS NULL)
     OR v_session.mode_id <> v_handoff.target_mode_id
     OR (v_handoff.execution_session_id IS NOT NULL
         AND v_handoff.execution_session_id <> v_session_id)
     OR (v_handoff.execution_session_id IS NOT NULL AND p_execution_session_id IS NOT NULL
         AND v_handoff.execution_session_id <> p_execution_session_id)
     THEN
    UPDATE public.mode_handoffs SET execution_failed_at=v_now,
      execution_failure_reason='session_unavailable' WHERE handoff_id=p_handoff_id;
    RETURN jsonb_build_object('status','unavailable','terminal',TRUE); END IF;
  IF (v_handoff.target_mode_id <> 'daily' AND v_handoff.target_grant_required AND NOT EXISTS (
       SELECT 1 FROM public.mode_grants WHERE user_id=p_user_id AND mode_id=v_handoff.target_mode_id
         AND revoked_at IS NULL AND expires_at > v_now)) THEN
    UPDATE public.mode_handoffs SET execution_failed_at=v_now,
      execution_failure_reason='target_unavailable' WHERE handoff_id=p_handoff_id;
    RETURN jsonb_build_object('status','unavailable','terminal',TRUE); END IF;
  UPDATE public.mode_handoffs SET execution_claimed_at=v_now,
    execution_claim_token=pg_catalog.gen_random_uuid(), execution_worker_id=p_worker_id,
    execution_session_id=v_session_id, execution_clock_at=coalesce(execution_clock_at, v_now),
    execution_attempts=execution_attempts+1 WHERE handoff_id=p_handoff_id RETURNING * INTO v_handoff;
  RETURN jsonb_build_object('status','claimed','handoff',to_jsonb(v_handoff));
END $$;
CREATE FUNCTION public.save_handoff_execution_plan(
  p_user_id UUID, p_handoff_id UUID, p_claim_token UUID, p_plan JSONB
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_row public.mode_handoffs%ROWTYPE; BEGIN
  IF p_plan IS NULL OR jsonb_typeof(p_plan) <> 'array' OR jsonb_array_length(p_plan) > 32 THEN
    RETURN FALSE; END IF;
  SELECT * INTO v_row FROM public.mode_handoffs WHERE user_id=p_user_id AND handoff_id=p_handoff_id
    AND execution_claim_token=p_claim_token AND executed_at IS NULL
    AND execution_failed_at IS NULL FOR UPDATE;
  IF NOT FOUND OR v_row.execution_claimed_at <= clock_timestamp()-interval '5 minutes'
    THEN RETURN FALSE; END IF;
  IF p_plan = v_row.execution_plan THEN RETURN TRUE; END IF;
  IF jsonb_array_length(p_plan) <> jsonb_array_length(v_row.execution_plan)+1
     OR (p_plan - (jsonb_array_length(p_plan)-1)) <> v_row.execution_plan THEN RETURN FALSE; END IF;
  UPDATE public.mode_handoffs SET execution_plan=p_plan WHERE handoff_id=p_handoff_id;
  RETURN TRUE;
END $$;
CREATE FUNCTION public.complete_handoff_execution(p_user_id UUID, p_handoff_id UUID, p_claim_token UUID)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_row public.mode_handoffs%ROWTYPE; BEGIN
  SELECT * INTO v_row FROM public.mode_handoffs WHERE user_id=p_user_id AND handoff_id=p_handoff_id
    AND execution_claim_token=p_claim_token AND executed_at IS NULL
    AND execution_failed_at IS NULL FOR UPDATE;
  IF NOT FOUND OR v_row.execution_claimed_at <= clock_timestamp()-interval '5 minutes'
    THEN RETURN FALSE; END IF;
  UPDATE public.mode_handoffs SET executed_at=clock_timestamp() WHERE handoff_id=p_handoff_id;
  RETURN TRUE;
END $$;
CREATE FUNCTION public.fail_handoff_execution(
 p_user_id UUID,p_handoff_id UUID,p_claim_token UUID,p_reason TEXT
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_row public.mode_handoffs%ROWTYPE; BEGIN
 IF p_reason IS NULL OR p_reason NOT IN ('execution_failed','attempts_exhausted','target_unavailable')
 THEN RETURN FALSE; END IF;
 SELECT * INTO v_row FROM public.mode_handoffs WHERE user_id=p_user_id AND handoff_id=p_handoff_id
   AND execution_claim_token=p_claim_token AND executed_at IS NULL
   AND execution_failed_at IS NULL FOR UPDATE;
 IF NOT FOUND OR v_row.execution_claimed_at <= clock_timestamp()-interval '5 minutes'
 THEN RETURN FALSE; END IF;
 UPDATE public.mode_handoffs SET execution_failed_at=clock_timestamp(),execution_failure_reason=p_reason
 WHERE handoff_id=p_handoff_id;
 RETURN TRUE;
END $$;
CREATE FUNCTION public.append_handoff_execution_message(
 p_user_id UUID,p_handoff_id UUID,p_claim_token UUID,p_role TEXT,p_content TEXT,p_channel TEXT
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE h public.mode_handoffs%ROWTYPE; v_message_id UUID; v_session_id UUID; BEGIN
 IF p_role IS NULL OR p_role NOT IN ('user','assistant') OR p_content IS NULL OR p_channel IS NULL
 THEN RETURN NULL; END IF;
 -- Keep the existing claim order: owned profile/Session before the handoff row.
 PERFORM 1 FROM public.user_profiles WHERE user_id=p_user_id FOR KEY SHARE;
 SELECT execution_session_id INTO v_session_id FROM public.mode_handoffs
 WHERE user_id=p_user_id AND handoff_id=p_handoff_id;
 PERFORM 1 FROM public.sessions s WHERE s.session_id=v_session_id AND s.user_id=p_user_id FOR KEY SHARE;
 SELECT * INTO h FROM public.mode_handoffs WHERE user_id=p_user_id AND handoff_id=p_handoff_id
 AND execution_claim_token=p_claim_token AND executed_at IS NULL AND execution_failed_at IS NULL
 FOR UPDATE;
 IF NOT FOUND OR h.execution_claimed_at<=clock_timestamp()-interval '5 minutes' THEN RETURN NULL; END IF;
 v_message_id:=CASE WHEN p_role='user' THEN h.execution_user_message_id
                  ELSE h.execution_assistant_message_id END;
 IF v_message_id IS NOT NULL THEN
   IF NOT EXISTS(SELECT 1 FROM public.messages m WHERE m.message_id=v_message_id AND m.user_id=p_user_id
     AND m.session_id=h.execution_session_id AND m.role=p_role AND m.content=p_content)
   THEN RETURN NULL; END IF;
 ELSE
   INSERT INTO public.messages(session_id,user_id,role,content,channel)
   VALUES(h.execution_session_id,p_user_id,p_role,p_content,p_channel)
   RETURNING public.messages.message_id INTO v_message_id;
   IF p_role='user' THEN UPDATE public.mode_handoffs SET execution_user_message_id=v_message_id
     WHERE handoff_id=p_handoff_id;
   ELSE UPDATE public.mode_handoffs SET execution_assistant_message_id=v_message_id
     WHERE handoff_id=p_handoff_id; END IF;
 END IF;
 RETURN jsonb_build_object('message_id',v_message_id);
END $$;
CREATE FUNCTION public.claim_handoff_failure_notice(
 p_user_id UUID,p_handoff_id UUID,p_outcome TEXT DEFAULT 'attempted'
) RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$ BEGIN
 IF p_outcome IS NULL OR p_outcome NOT IN ('attempted','endpoint_unavailable','owner_unavailable')
 THEN RETURN FALSE; END IF;
 UPDATE public.mode_handoffs SET execution_failure_notice_at=clock_timestamp(),
 execution_failure_notice_outcome=p_outcome WHERE user_id=p_user_id AND handoff_id=p_handoff_id
 AND execution_failed_at IS NOT NULL AND execution_failure_notice_at IS NULL;
 RETURN FOUND;
END $$;
CREATE FUNCTION public.list_pending_handoff_failure_notices(p_limit INT DEFAULT 25)
RETURNS TABLE(user_id UUID,handoff_id UUID)
LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
 SELECT h.user_id,h.handoff_id FROM public.mode_handoffs h
 WHERE h.execution_failed_at IS NOT NULL AND h.execution_failure_notice_at IS NULL
 ORDER BY h.execution_failed_at LIMIT greatest(1,least(p_limit,100));
$$;
CREATE FUNCTION public.list_pending_handoff_executions(p_limit INT DEFAULT 25)
RETURNS TABLE(user_id UUID, handoff_id UUID, execution_session_id UUID, target_mode_id TEXT,
              telegram_chat_id BIGINT)
LANGUAGE sql SECURITY DEFINER SET search_path = '' AS $$
  SELECT h.user_id, h.handoff_id, h.execution_session_id, h.target_mode_id, u.telegram_chat_id
  FROM public.mode_handoffs h JOIN public.user_profiles u ON u.user_id=h.user_id
  WHERE h.resolution='confirmed' AND h.executed_at IS NULL AND h.execution_failed_at IS NULL
    AND (h.execution_claimed_at IS NULL OR h.execution_claimed_at <= clock_timestamp()-interval '5 minutes')
  ORDER BY h.created_at LIMIT greatest(1, least(p_limit,100));
$$;

REVOKE ALL ON FUNCTION public.save_mode_conversation(UUID,TEXT,TEXT,JSONB,BOOLEAN),
 public.close_mode_conversation(UUID,TEXT,TEXT),
 public.claim_handoff_execution(UUID,UUID,TEXT,UUID),
 public.save_handoff_execution_plan(UUID,UUID,UUID,JSONB),
 public.complete_handoff_execution(UUID,UUID,UUID),
 public.fail_handoff_execution(UUID,UUID,UUID,TEXT), public.list_pending_handoff_executions(INT),
 public.append_handoff_execution_message(UUID,UUID,UUID,TEXT,TEXT,TEXT),
 public.claim_handoff_failure_notice(UUID,UUID,TEXT), public.list_pending_handoff_failure_notices(INT)
 FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.save_mode_conversation(UUID,TEXT,TEXT,JSONB,BOOLEAN),
 public.close_mode_conversation(UUID,TEXT,TEXT),
 public.claim_handoff_execution(UUID,UUID,TEXT,UUID),
 public.save_handoff_execution_plan(UUID,UUID,UUID,JSONB),
 public.complete_handoff_execution(UUID,UUID,UUID),
 public.fail_handoff_execution(UUID,UUID,UUID,TEXT), public.list_pending_handoff_executions(INT),
 public.append_handoff_execution_message(UUID,UUID,UUID,TEXT,TEXT,TEXT),
 public.claim_handoff_failure_notice(UUID,UUID,TEXT), public.list_pending_handoff_failure_notices(INT)
 TO service_role;
DO $$ BEGIN
 IF to_regclass('public.mode_conversations') IS NULL
    OR to_regclass('public.mode_conversation_endpoints') IS NULL
    OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute WHERE attrelid='public.sessions'::regclass
      AND attname='mode_id' AND NOT attisdropped)
    OR NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute WHERE attrelid='public.mode_handoffs'::regclass
      AND attname='execution_plan' AND NOT attisdropped)
    OR to_regprocedure('public.claim_handoff_execution(uuid,uuid,text,uuid)') IS NULL
    OR to_regprocedure('public.complete_handoff_execution(uuid,uuid,uuid)') IS NULL
    OR to_regprocedure('public.save_handoff_execution_plan(uuid,uuid,uuid,jsonb)') IS NULL
    OR to_regprocedure('public.fail_handoff_execution(uuid,uuid,uuid,text)') IS NULL
    OR to_regprocedure('public.append_handoff_execution_message(uuid,uuid,uuid,text,text,text)') IS NULL
    OR to_regprocedure('public.claim_handoff_failure_notice(uuid,uuid,text)') IS NULL
    OR to_regprocedure('public.list_pending_handoff_failure_notices(integer)') IS NULL
 THEN RAISE EXCEPTION '017 objects were not created'; END IF;
 INSERT INTO public.schema_migrations(version) VALUES(17);
END $$;
COMMIT;
