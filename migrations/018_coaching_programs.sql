BEGIN;
DO $$ BEGIN
 IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 17) <> 17
    OR (SELECT max(version) FROM public.schema_migrations) <> 17 THEN
  RAISE EXCEPTION '018 requires the complete approved 001-017 chain'; END IF;
END $$;
CREATE TABLE public.coaching_programs (
 program_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
 user_id UUID NOT NULL REFERENCES public.user_profiles(user_id),
 goal TEXT NOT NULL CHECK(char_length(btrim(goal)) BETWEEN 1 AND 2000),
 success_measure TEXT NOT NULL CHECK(char_length(btrim(success_measure)) BETWEEN 1 AND 2000),
 check_in_days INT[] NOT NULL CHECK(cardinality(check_in_days) BETWEEN 1 AND 7
   AND check_in_days <@ ARRAY[1,2,3,4,5,6,7]),
 check_in_time TEXT NOT NULL CHECK(check_in_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
 timezone TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('draft','active','paused','completed','stopped')),
 starts_at TIMESTAMPTZ, ends_at TIMESTAMPTZ, extended_count INT NOT NULL DEFAULT 0 CHECK(extended_count>=0),
 version INT NOT NULL DEFAULT 1 CHECK(version>0),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 CHECK((starts_at IS NULL AND ends_at IS NULL) OR (starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at>starts_at)),
 CHECK(state NOT IN ('active','paused','completed') OR starts_at IS NOT NULL),
 UNIQUE(program_id,user_id)
);
CREATE UNIQUE INDEX coaching_one_nonterminal ON public.coaching_programs(user_id)
 WHERE state NOT IN ('completed','stopped');
CREATE TABLE public.coaching_entries (
 entry_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), user_id UUID NOT NULL,
 program_id UUID NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('lifecycle','progress','weekly_choice','delivery')),
 action TEXT, participant_text TEXT, choice TEXT, extension_days INT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(program_id,user_id) REFERENCES public.coaching_programs(program_id,user_id) ON DELETE CASCADE,
 CHECK(kind <> 'progress' OR (participant_text IS NOT NULL
   AND char_length(btrim(participant_text)) BETWEEN 1 AND 4000)),
 CHECK(kind <> 'weekly_choice' OR choice IS NOT NULL),
 CHECK(kind <> 'lifecycle' OR action IS NOT NULL),
 CHECK(choice IS NULL OR choice IN ('continue','adjust','pause','stop'))
);
CREATE TABLE public.coaching_approvals (
 token_hash TEXT PRIMARY KEY, user_id UUID NOT NULL, program_id UUID NOT NULL,
 version INT NOT NULL, summary_digest TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
 used_at TIMESTAMPTZ,
 FOREIGN KEY(program_id,user_id) REFERENCES public.coaching_programs(program_id,user_id) ON DELETE CASCADE
);
CREATE TABLE public.coaching_command_receipts (
 user_id UUID NOT NULL, idempotency_key TEXT NOT NULL, program_id UUID NOT NULL,
 payload_hash TEXT NOT NULL, result JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(user_id,idempotency_key),
 FOREIGN KEY(program_id,user_id) REFERENCES public.coaching_programs(program_id,user_id) ON DELETE CASCADE
);
ALTER TABLE public.coaching_programs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coaching_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coaching_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coaching_command_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.coaching_programs,public.coaching_entries,public.coaching_approvals,
 public.coaching_command_receipts FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.coaching_programs,public.coaching_entries TO authenticated,service_role;
CREATE POLICY coaching_programs_own ON public.coaching_programs FOR SELECT TO authenticated
 USING(user_id=(SELECT user_id FROM public.user_profiles WHERE supabase_auth_id=auth.uid()));
CREATE POLICY coaching_entries_own ON public.coaching_entries FOR SELECT TO authenticated
 USING(user_id=(SELECT user_id FROM public.user_profiles WHERE supabase_auth_id=auth.uid()));

CREATE FUNCTION public.coaching_digest(p_value JSONB) RETURNS TEXT
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT encode(sha256(convert_to(p_value::TEXT,'UTF8')),'hex');
$$;
CREATE FUNCTION public.coaching_valid_configuration(p_data JSONB) RETURNS BOOLEAN
LANGUAGE plpgsql STABLE SET search_path='' AS $$ BEGIN
 IF jsonb_typeof(p_data) IS DISTINCT FROM 'object'
    OR jsonb_typeof(p_data->'goal') IS DISTINCT FROM 'string'
    OR jsonb_typeof(p_data->'success_measure') IS DISTINCT FROM 'string'
    OR char_length(btrim(p_data->>'goal')) NOT BETWEEN 1 AND 2000
    OR char_length(btrim(p_data->>'success_measure')) NOT BETWEEN 1 AND 2000
    OR jsonb_typeof(p_data->'check_in_days') IS DISTINCT FROM 'array'
    OR jsonb_array_length(p_data->'check_in_days') NOT BETWEEN 1 AND 7 THEN RETURN FALSE; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(p_data->'check_in_days') AS d(value)
           WHERE jsonb_typeof(value)<>'number' OR value::TEXT !~ '^[1-7]$')
    OR (SELECT count(DISTINCT value) FROM jsonb_array_elements(p_data->'check_in_days') AS d(value))
       <> jsonb_array_length(p_data->'check_in_days')
    OR (p_data->>'check_in_time') IS NULL OR (p_data->>'check_in_time') !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'
    OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name=p_data->>'timezone')
 THEN RETURN FALSE; END IF;
 RETURN TRUE;
END $$;
CREATE FUNCTION public.coaching_program_command(
 p_user_id UUID, p_program_id UUID, p_expected_version INT, p_action TEXT,
 p_idempotency_key TEXT, p_payload_hash TEXT, p_data JSONB DEFAULT '{}'::jsonb
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.coaching_programs%ROWTYPE; e public.coaching_entries%ROWTYPE;
 receipt public.coaching_command_receipts%ROWTYPE; approval public.coaching_approvals%ROWTYPE;
 v_now TIMESTAMPTZ; v_days INT[]; v_kind TEXT:='lifecycle'; v_action TEXT;
 v_progress TEXT; v_choice TEXT; v_extension INT; v_result JSONB;
BEGIN
 IF p_idempotency_key IS NULL OR btrim(p_idempotency_key)='' OR p_payload_hash IS NULL
    OR p_payload_hash='' OR p_action IS NULL OR jsonb_typeof(p_data) IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION 'invalid_coaching_command'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-coach:'||p_user_id::TEXT,0));
 SELECT * INTO receipt FROM public.coaching_command_receipts
  WHERE user_id=p_user_id AND idempotency_key=p_idempotency_key;
 IF FOUND THEN
  IF receipt.payload_hash<>p_payload_hash THEN RAISE EXCEPTION 'idempotency_key_conflict'; END IF;
  RETURN receipt.result;
 END IF;
 v_now:=clock_timestamp();
 IF p_action='draft' THEN
  IF NOT public.coaching_valid_configuration(p_data) THEN RAISE EXCEPTION 'invalid_coaching_config'; END IF;
  IF EXISTS(SELECT 1 FROM public.coaching_programs WHERE user_id=p_user_id
            AND state NOT IN ('completed','stopped')) THEN RAISE EXCEPTION 'coaching_invalid_transition'; END IF;
  SELECT array_agg(value::INT ORDER BY value::INT) INTO v_days
   FROM jsonb_array_elements_text(p_data->'check_in_days');
  INSERT INTO public.coaching_programs(user_id,goal,success_measure,check_in_days,check_in_time,timezone,state,
                                     created_at,updated_at)
   VALUES(p_user_id,p_data->>'goal',p_data->>'success_measure',v_days,p_data->>'check_in_time',
          p_data->>'timezone','draft',v_now,v_now) RETURNING * INTO r;
 ELSE
  SELECT * INTO r FROM public.coaching_programs WHERE program_id=p_program_id AND user_id=p_user_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'coaching_program_unavailable'; END IF;
  IF p_expected_version IS NULL OR r.version<>p_expected_version THEN RAISE EXCEPTION 'coaching_stale_version'; END IF;
  v_now:=clock_timestamp();
  IF r.state IN ('completed','stopped') OR (r.ends_at IS NOT NULL AND r.ends_at<=v_now)
   THEN RAISE EXCEPTION 'coaching_invalid_transition'; END IF;
  IF p_action='activate' THEN
   SELECT * INTO approval FROM public.coaching_approvals
    WHERE token_hash=public.coaching_digest(to_jsonb(p_data->>'approval_token')) FOR UPDATE;
   IF NOT FOUND OR r.state<>'draft' OR approval.user_id<>p_user_id OR approval.program_id<>r.program_id
      OR approval.version<>r.version OR approval.summary_digest<>public.coaching_digest(to_jsonb(r))
      OR approval.used_at IS NOT NULL OR approval.expires_at<=clock_timestamp()
    THEN RAISE EXCEPTION 'coaching_approval_required'; END IF;
   UPDATE public.coaching_approvals SET used_at=clock_timestamp() WHERE token_hash=approval.token_hash;
   r.state:='active'; r.starts_at:=coalesce(r.starts_at,v_now); r.ends_at:=coalesce(r.ends_at,v_now+interval '336 hours');
  ELSIF p_action='pause' AND r.state='active' THEN r.state:='paused';
  ELSIF p_action='resume' AND r.state='paused' THEN r.state:='active';
  ELSIF p_action='stop' THEN r.state:='stopped';
  ELSIF p_action='extend' AND r.state IN ('active','paused') THEN
   IF jsonb_typeof(p_data->'extension_days') IS DISTINCT FROM 'number'
      OR (p_data->>'extension_days') !~ '^([1-9]|1[0-4])$' THEN RAISE EXCEPTION 'invalid_coaching_extension'; END IF;
   v_extension:=(p_data->>'extension_days')::INT;
   r.ends_at:=r.ends_at+v_extension*interval '24 hours'; r.extended_count:=r.extended_count+1;
  ELSIF p_action='record_progress' AND r.state IN ('active','paused') THEN
   IF jsonb_typeof(p_data->'progress_text') IS DISTINCT FROM 'string'
      OR char_length(btrim(p_data->>'progress_text')) NOT BETWEEN 1 AND 4000
    THEN RAISE EXCEPTION 'invalid_coaching_progress'; END IF;
   v_kind:='progress'; v_progress:=p_data->>'progress_text';
  ELSIF p_action='record_weekly_choice' AND r.state='active' THEN
   v_choice:=p_data->>'weekly_choice';
   IF v_choice IS NULL OR v_choice NOT IN ('continue','adjust','pause','stop') THEN RAISE EXCEPTION 'invalid_coaching_choice'; END IF;
   IF v_choice IN ('adjust','pause') THEN r.state:='paused'; ELSIF v_choice='stop' THEN r.state:='stopped'; END IF;
   v_kind:='weekly_choice';
  ELSIF p_action='revise' AND r.state IN ('draft','paused') THEN
   IF NOT public.coaching_valid_configuration(p_data) THEN RAISE EXCEPTION 'invalid_coaching_config'; END IF;
   SELECT array_agg(value::INT ORDER BY value::INT) INTO v_days
    FROM jsonb_array_elements_text(p_data->'check_in_days');
   r.goal:=p_data->>'goal'; r.success_measure:=p_data->>'success_measure'; r.check_in_days:=v_days;
   r.check_in_time:=p_data->>'check_in_time'; r.timezone:=p_data->>'timezone'; r.state:='draft';
  ELSE RAISE EXCEPTION 'coaching_invalid_transition'; END IF;
  UPDATE public.coaching_programs SET state=r.state,starts_at=r.starts_at,ends_at=r.ends_at,
   extended_count=r.extended_count,goal=r.goal,success_measure=r.success_measure,
   check_in_days=r.check_in_days,check_in_time=r.check_in_time,timezone=r.timezone,
   version=version+1,updated_at=clock_timestamp() WHERE program_id=r.program_id RETURNING * INTO r;
 END IF;
 v_action:=CASE WHEN v_kind='lifecycle' THEN p_action ELSE NULL END;
 INSERT INTO public.coaching_entries(user_id,program_id,kind,action,participant_text,choice,extension_days)
  VALUES(p_user_id,r.program_id,v_kind,v_action,v_progress,v_choice,v_extension) RETURNING * INTO e;
 v_result:=jsonb_build_object('program',to_jsonb(r),'entry',to_jsonb(e));
 INSERT INTO public.coaching_command_receipts(user_id,idempotency_key,program_id,payload_hash,result)
  VALUES(p_user_id,p_idempotency_key,r.program_id,p_payload_hash,v_result);
 RETURN v_result;
END $$;
CREATE FUNCTION public.issue_coaching_approval(p_user_id UUID,p_program_id UUID,p_expected_version INT)
RETURNS TEXT LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.coaching_programs%ROWTYPE; token TEXT; BEGIN
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-coach:'||p_user_id::TEXT,0));
 SELECT * INTO r FROM public.coaching_programs WHERE user_id=p_user_id AND program_id=p_program_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'coaching_program_unavailable'; END IF;
 IF r.version IS DISTINCT FROM p_expected_version THEN RAISE EXCEPTION 'coaching_stale_version'; END IF;
 IF r.state<>'draft' THEN RAISE EXCEPTION 'coaching_invalid_transition'; END IF;
 token:=pg_catalog.gen_random_uuid()::TEXT;
 INSERT INTO public.coaching_approvals(token_hash,user_id,program_id,version,summary_digest,expires_at)
  VALUES(public.coaching_digest(to_jsonb(token)),p_user_id,p_program_id,p_expected_version,
         public.coaching_digest(to_jsonb(r)),clock_timestamp()+interval '10 minutes');
 RETURN token;
END $$;
CREATE FUNCTION public.confirm_coaching_approval(p_user_id UUID,p_token TEXT,p_idempotency_key TEXT,p_payload_hash TEXT)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE a public.coaching_approvals%ROWTYPE; BEGIN
 SELECT * INTO a FROM public.coaching_approvals WHERE user_id=p_user_id AND token_hash=public.coaching_digest(to_jsonb(p_token));
 IF NOT FOUND THEN RAISE EXCEPTION 'coaching_approval_required'; END IF;
 RETURN public.coaching_program_command(p_user_id,a.program_id,a.version,'activate',p_idempotency_key,p_payload_hash,
                                       jsonb_build_object('approval_token',p_token));
END $$;
CREATE FUNCTION public.complete_due_coaching_programs() RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.coaching_programs%ROWTYPE; result JSONB:='[]'::jsonb; v_now TIMESTAMPTZ; BEGIN
 -- Each owner uses the same serialization order as program mutations/deletion.
 FOR r IN SELECT * FROM public.coaching_programs WHERE state NOT IN ('completed','stopped')
          AND ends_at<=clock_timestamp() ORDER BY user_id LOOP
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-coach:'||r.user_id::TEXT,0));
  v_now:=clock_timestamp();
  UPDATE public.coaching_programs SET state='completed',version=version+1,updated_at=v_now
   WHERE program_id=r.program_id AND state NOT IN ('completed','stopped') AND ends_at<=v_now RETURNING * INTO r;
  IF FOUND THEN
   INSERT INTO public.coaching_entries(user_id,program_id,kind,action) VALUES(r.user_id,r.program_id,'lifecycle','complete');
   result:=result||jsonb_build_array(jsonb_build_object('user_id',r.user_id,'program_id',r.program_id));
  END IF;
 END LOOP;
 RETURN result;
END $$;
CREATE FUNCTION public.export_coaching_data(p_user_id UUID) RETURNS JSONB
LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT jsonb_build_object('programs',coalesce((SELECT jsonb_agg(to_jsonb(p) ORDER BY p.created_at)
  FROM public.coaching_programs p WHERE p.user_id=p_user_id),'[]'::jsonb),
  'entries',coalesce((SELECT jsonb_agg(to_jsonb(e) ORDER BY e.created_at)
  FROM public.coaching_entries e WHERE e.user_id=p_user_id),'[]'::jsonb));
$$;
CREATE FUNCTION public.delete_coaching_data(p_user_id UUID,p_verified_request_id TEXT) RETURNS VOID
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN
 IF p_verified_request_id IS NULL OR btrim(p_verified_request_id)='' THEN RAISE EXCEPTION 'verified_deletion_required'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-coach:'||p_user_id::TEXT,0));
 DELETE FROM public.coaching_programs WHERE user_id=p_user_id;
END $$;
REVOKE ALL ON FUNCTION public.coaching_digest(JSONB),public.coaching_valid_configuration(JSONB)
 FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.coaching_program_command(UUID,UUID,INT,TEXT,TEXT,TEXT,JSONB),
 public.issue_coaching_approval(UUID,UUID,INT),public.confirm_coaching_approval(UUID,TEXT,TEXT,TEXT),
 public.complete_due_coaching_programs(),public.export_coaching_data(UUID),public.delete_coaching_data(UUID,TEXT)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.coaching_program_command(UUID,UUID,INT,TEXT,TEXT,TEXT,JSONB),
 public.issue_coaching_approval(UUID,UUID,INT),public.confirm_coaching_approval(UUID,TEXT,TEXT,TEXT),
 public.complete_due_coaching_programs(),public.export_coaching_data(UUID),public.delete_coaching_data(UUID,TEXT)
 TO service_role;
DO $$ BEGIN
 IF to_regclass('public.coaching_programs') IS NULL OR to_regclass('public.coaching_entries') IS NULL
    OR to_regclass('public.coaching_approvals') IS NULL OR to_regclass('public.coaching_command_receipts') IS NULL
    OR to_regprocedure('public.coaching_program_command(uuid,uuid,integer,text,text,text,jsonb)') IS NULL
    OR to_regprocedure('public.confirm_coaching_approval(uuid,text,text,text)') IS NULL
 THEN RAISE EXCEPTION '018 objects were not created'; END IF;
 INSERT INTO public.schema_migrations(version) VALUES(18);
END $$;
COMMIT;
