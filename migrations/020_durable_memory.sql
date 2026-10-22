BEGIN;
DO $$ BEGIN
 IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 19) <> 19
 OR (SELECT max(version) FROM public.schema_migrations) <> 19 THEN
 RAISE EXCEPTION '020 requires the complete approved 001-019 chain'; END IF;
END $$;
-- Owner-reviewed eligibility/notice/rights readiness. No service-role setter exists.
CREATE TABLE public.memory_admission_controls (
 singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton), ready BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO public.memory_admission_controls DEFAULT VALUES;
CREATE TABLE public.memory_settings (
 user_id UUID PRIMARY KEY REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 enabled BOOLEAN NOT NULL DEFAULT FALSE, learning_paused BOOLEAN NOT NULL DEFAULT FALSE,
 use_paused BOOLEAN NOT NULL DEFAULT FALSE, policy_version TEXT, opted_in_at TIMESTAMPTZ,
 version INT NOT NULL DEFAULT 0 CHECK(version>=0),
 CHECK(NOT enabled OR (policy_version='memory-explicit-v1' AND opted_in_at IS NOT NULL))
);
CREATE TABLE public.memory_versions (
 memory_id UUID NOT NULL, version INT NOT NULL CHECK(version>0),
 user_id UUID NOT NULL REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 category TEXT NOT NULL CHECK(category IN ('preference','routine','constraint','goal','project','context')),
 text TEXT, source_mode_id TEXT, source_channel TEXT, source_message_id UUID,
 source_date DATE, creation_path TEXT, scopes TEXT[] NOT NULL, valid_until DATE,
 reconfirm_at TIMESTAMPTZ, state TEXT NOT NULL CHECK(state IN
 ('active','needs_confirmation','inactive','superseded','expired','forgotten')),
 goal_state TEXT NOT NULL DEFAULT 'ongoing' CHECK(goal_state IN ('ongoing','completed','cancelled')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), confirmed_at TIMESTAMPTZ NOT NULL,
 supersedes_version INT, PRIMARY KEY(memory_id,version), UNIQUE(user_id,memory_id,version),
 CHECK((state='forgotten' AND text IS NULL AND source_mode_id IS NULL AND source_channel IS NULL
   AND source_message_id IS NULL AND source_date IS NULL AND creation_path IS NULL
   AND cardinality(scopes)=0 AND valid_until IS NULL AND reconfirm_at IS NULL)
 OR (state<>'forgotten' AND text IS NOT NULL AND source_mode_id IS NOT NULL
   AND source_channel IS NOT NULL AND creation_path IS NOT NULL AND char_length(btrim(text)) BETWEEN 1 AND 2000
   AND source_mode_id ~ '^[a-z][a-z0-9_]{0,31}$' AND source_channel ~ '^[a-z][a-z0-9_]{0,31}$'
   AND source_date IS NOT NULL AND creation_path IN
    ('participant_requested','amigo_proposed','dashboard_explicit') AND cardinality(scopes) BETWEEN 1 AND 4))
);
CREATE INDEX memory_owned_scope ON public.memory_versions(user_id,state);
CREATE TABLE public.memory_uses (
 user_id UUID NOT NULL, memory_id UUID NOT NULL, version INT NOT NULL, turn_id TEXT NOT NULL,
 purpose TEXT NOT NULL CHECK(purpose IN ('personalize','suggestion','preference')),
 used_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY(user_id,memory_id,version,turn_id),
 FOREIGN KEY(user_id,memory_id,version) REFERENCES public.memory_versions(user_id,memory_id,version)
 ON DELETE CASCADE
);
CREATE TABLE public.memory_confirmation_claims (
 token_hash TEXT PRIMARY KEY, user_id UUID NOT NULL REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 operation TEXT NOT NULL CHECK(operation IN ('save','correct','reconfirm','share','forget_all')),
 preview_digest TEXT NOT NULL, settings_version INT NOT NULL,
 memory_id UUID, memory_version INT, expires_at TIMESTAMPTZ NOT NULL, consumed_at TIMESTAMPTZ
);
CREATE TABLE public.memory_command_receipts (
 user_id UUID NOT NULL REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 idempotency_key TEXT NOT NULL, payload_hash TEXT, operation TEXT NOT NULL,
 memory_id UUID, version INT, result_metadata JSONB,
 PRIMARY KEY(user_id,idempotency_key)
);
-- No plaintext preview or result copies. All data operations use the serialized RPC below.
ALTER TABLE public.memory_admission_controls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_uses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_confirmation_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_command_receipts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.memory_admission_controls,public.memory_settings,public.memory_versions,
 public.memory_uses,public.memory_confirmation_claims,public.memory_command_receipts
 FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION public.memory_effective_state(p_row public.memory_versions,p_timezone TEXT)
RETURNS TEXT LANGUAGE SQL STABLE SET search_path='' AS $$
 SELECT CASE WHEN p_row.state<>'active' THEN p_row.state
 WHEN p_row.valid_until < (clock_timestamp() AT TIME ZONE p_timezone)::DATE THEN 'expired'
 WHEN p_row.reconfirm_at <= clock_timestamp() THEN 'needs_confirmation'
 WHEN p_row.goal_state<>'ongoing' THEN 'inactive' ELSE 'active' END
$$;
CREATE FUNCTION public.memory_normalize_payload(p JSONB) RETURNS JSONB
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
DECLARE s TEXT[]; f TEXT; BEGIN
 IF jsonb_typeof(p) IS DISTINCT FROM 'object' OR EXISTS(SELECT 1 FROM jsonb_object_keys(p) k WHERE k NOT IN
 ('category','text','source_mode_id','source_channel','source_message_id','source_date','creation_path','scopes','valid_until'))
 OR p->>'category' IS NULL OR p->>'category' NOT IN ('preference','routine','constraint','goal','project','context')
 OR jsonb_typeof(p->'text') IS DISTINCT FROM 'string' OR char_length(btrim(p->>'text')) NOT BETWEEN 1 AND 2000
 OR p->>'creation_path' IS NULL OR p->>'creation_path' NOT IN ('participant_requested','amigo_proposed','dashboard_explicit')
 OR jsonb_typeof(p->'scopes') IS DISTINCT FROM 'array'
 THEN RAISE EXCEPTION 'Invalid Memory payload'; END IF;
 FOREACH f IN ARRAY ARRAY['source_mode_id','source_channel'] LOOP
 IF jsonb_typeof(p->f) IS DISTINCT FROM 'string' OR (p->>f) !~ '^[a-z][a-z0-9_]{0,31}$'
 THEN RAISE EXCEPTION 'Invalid Memory provenance'; END IF; END LOOP;
 IF jsonb_array_length(p->'scopes') NOT BETWEEN 1 AND 4 OR EXISTS
 (SELECT 1 FROM jsonb_array_elements(p->'scopes') x WHERE jsonb_typeof(x)<>'string'
 OR (x#>>'{}') !~ '^[a-z][a-z0-9_]{0,31}$') THEN RAISE EXCEPTION 'Invalid Memory scope'; END IF;
 SELECT array_agg(DISTINCT value COLLATE "C" ORDER BY value COLLATE "C") INTO s FROM jsonb_array_elements_text(p->'scopes');
 IF p->>'source_date' IS NULL OR to_char((p->>'source_date')::DATE,'YYYY-MM-DD')<>p->>'source_date'
 OR (p->>'valid_until' IS NOT NULL AND to_char((p->>'valid_until')::DATE,'YYYY-MM-DD')<>p->>'valid_until')
 THEN RAISE EXCEPTION 'Invalid Memory date'; END IF;
 RETURN jsonb_build_object('category',p->>'category','text',p->>'text',
 'source_mode_id',p->>'source_mode_id','source_channel',p->>'source_channel',
 'source_message_id',(p->>'source_message_id')::UUID,'source_date',p->>'source_date',
 'creation_path',p->>'creation_path','scopes',to_jsonb(s),'valid_until',p->>'valid_until');
EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
 RAISE EXCEPTION 'Invalid Memory input';
END $$;
CREATE FUNCTION public.memory_payload_digest(p JSONB) RETURNS TEXT
LANGUAGE SQL IMMUTABLE SET search_path='' AS $$
 SELECT encode(sha256(convert_to(jsonb_build_array(v->'category',v->'text',v->'source_mode_id',
 v->'source_channel',v->'source_message_id',v->'source_date',v->'creation_path',v->'scopes',
 v->'valid_until')::TEXT,'UTF8')),'hex') FROM (SELECT public.memory_normalize_payload(p) v) normalized
$$;
CREATE FUNCTION public.memory_inventory_digest(p_user_id UUID) RETURNS TEXT
LANGUAGE SQL STABLE SET search_path='' AS $$
 SELECT encode(sha256(convert_to(coalesce(jsonb_agg(jsonb_build_array(memory_id::TEXT,version)
 ORDER BY memory_id,version),'[]'::JSONB)::TEXT,'UTF8')),'hex')
 FROM public.memory_versions WHERE user_id=p_user_id AND state<>'forgotten'
$$;
CREATE FUNCTION public.memory_command(p_user_id UUID,p_operation TEXT,p_args JSONB DEFAULT '{}')
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE s public.memory_settings; m public.memory_versions; old public.memory_versions;
 c public.memory_confirmation_claims; r public.memory_command_receipts; v JSONB; result JSONB;
 token TEXT; key TEXT:=p_args->>'idempotency_key'; digest TEXT:=p_args->>'payload_hash';
 tz TEXT; ids UUID[]; n INT; action TEXT; rows JSONB; usage JSONB; previous UUID[];
BEGIN
 IF jsonb_typeof(p_args) IS DISTINCT FROM 'object' OR p_operation IS NULL OR p_operation NOT IN
 ('get_memory_settings','inspect_memories','export_memory_data','prepare_memory_confirmation',
 'read_memory_context','confirm_memory_save','set_memory_pauses','transition_memory',
 'forget_memory','confirm_forget_all_memory','disable_memory') THEN RAISE EXCEPTION 'Invalid Memory input'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_each(p_args) e WHERE e.key IN
 ('idempotency_key','payload_hash','token') AND e.value<>'null'::JSONB AND jsonb_typeof(e.value)<>'string')
 OR EXISTS(SELECT 1 FROM jsonb_each(p_args) e WHERE e.key IN
 ('learning','use','enable_memory') AND e.value<>'null'::JSONB AND jsonb_typeof(e.value)<>'boolean')
 THEN RAISE EXCEPTION 'Invalid Memory input'; END IF;
 -- Parent row before child/advisory locks prevents deletion/FK lock inversion.
 SELECT coalesce(timezone,'UTC') INTO tz FROM public.user_profiles WHERE user_id=p_user_id FOR KEY SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Memory owner unavailable'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('amigo-memory:'||p_user_id::TEXT,0));
 SELECT * INTO s FROM public.memory_settings WHERE user_id=p_user_id;
 IF NOT FOUND THEN s.user_id:=p_user_id; s.enabled:=FALSE; s.learning_paused:=FALSE;
 s.use_paused:=FALSE; s.version:=0; END IF;
 -- Every caller follows profile -> participant -> optional admission. Read enabled only
 -- under the participant lock, so a concurrent withdrawal cannot bypass the five-owner cap.
 IF p_operation='confirm_memory_save' AND NOT s.enabled THEN
   PERFORM pg_advisory_xact_lock(hashtextextended('amigo-memory-admission',0)); END IF;
 IF p_operation='get_memory_settings' THEN RETURN to_jsonb(s); END IF;
 IF p_operation IN ('confirm_memory_save','transition_memory','set_memory_pauses','forget_memory','confirm_forget_all_memory','disable_memory') THEN
 IF key IS NULL OR char_length(key) NOT BETWEEN 1 AND 200 OR digest IS NULL OR char_length(digest) NOT BETWEEN 1 AND 200
 THEN RAISE EXCEPTION 'Memory replay metadata required'; END IF;
 SELECT * INTO r FROM public.memory_command_receipts WHERE user_id=p_user_id AND idempotency_key=key;
 IF FOUND THEN
 IF r.payload_hash IS NULL THEN
   IF r.operation=p_operation AND (p_operation='confirm_forget_all_memory'
     OR (p_operation='forget_memory' AND r.result_metadata->>'memory_id'=p_args->>'memory_id'))
   THEN RETURN r.result_metadata; END IF;
   RAISE EXCEPTION 'idempotency key reused';
 END IF;
 IF r.payload_hash<>digest OR r.operation<>p_operation THEN RAISE EXCEPTION 'idempotency key reused'; END IF;
 IF r.version IS NOT NULL THEN SELECT * INTO m FROM public.memory_versions WHERE user_id=p_user_id
 AND memory_id=r.memory_id AND version=r.version;
 RETURN jsonb_build_object('memory',to_jsonb(m),'settings',to_jsonb(s)); END IF;
 RETURN r.result_metadata; END IF; END IF;
 IF p_operation IN ('inspect_memories','export_memory_data') THEN
 SELECT coalesce(jsonb_agg(value ORDER BY memory_id,version),'[]') INTO rows FROM
 (SELECT memory_id,version,to_jsonb(mv)||jsonb_build_object('state',public.memory_effective_state(mv,tz)) value
 FROM public.memory_versions mv WHERE user_id=p_user_id
 AND (p_args->>'states' IS NULL OR public.memory_effective_state(mv,tz) IN
 (SELECT jsonb_array_elements_text(p_args->'states')))
 ORDER BY memory_id,version LIMIT CASE WHEN p_operation='export_memory_data' THEN NULL
 ELSE greatest(1,least(coalesce((p_args->>'limit')::INT,100),1000)) END
 OFFSET CASE WHEN p_operation='export_memory_data' THEN 0 ELSE greatest(0,coalesce((p_args->>'offset')::INT,0)) END) page;
 SELECT coalesce(jsonb_agg(to_jsonb(mu) ORDER BY used_at),'[]') INTO usage FROM public.memory_uses mu WHERE user_id=p_user_id;
 RETURN jsonb_build_object('memories',rows,'uses',usage,'settings',to_jsonb(s));
 ELSIF p_operation='prepare_memory_confirmation' THEN
 IF s.version IS DISTINCT FROM (p_args->>'expected_settings_version')::INT THEN RAISE EXCEPTION 'stale version'; END IF;
 action:=p_args->>'operation';
 IF action IS NULL OR action NOT IN ('save','correct','reconfirm','share','forget_all')
 OR coalesce(p_args->>'preview_digest','') !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'Invalid Memory confirmation'; END IF;
 IF action<>'forget_all' AND (s.learning_paused OR NOT(SELECT ready FROM public.memory_admission_controls))
 THEN RAISE EXCEPTION 'invalid transition: Memory admission unavailable or learning paused'; END IF;
 IF action IN ('correct','reconfirm','share') THEN
 SELECT * INTO m FROM public.memory_versions WHERE user_id=p_user_id AND memory_id=(p_args->>'memory_id')::UUID ORDER BY version DESC LIMIT 1;
 IF NOT FOUND THEN RAISE EXCEPTION 'Memory unavailable'; END IF;
 IF m.version IS DISTINCT FROM (p_args->>'expected_memory_version')::INT THEN RAISE EXCEPTION 'stale version'; END IF; END IF;
 token:=replace(gen_random_uuid()::TEXT,'-','')||replace(gen_random_uuid()::TEXT,'-','');
 INSERT INTO public.memory_confirmation_claims VALUES(encode(sha256(convert_to(token,'UTF8')),'hex'),p_user_id,
 action,p_args->>'preview_digest',s.version,(p_args->>'memory_id')::UUID,
 (p_args->>'expected_memory_version')::INT,clock_timestamp()+INTERVAL '10 minutes',NULL);
 RETURN jsonb_build_object('token',token,'expires_at',clock_timestamp()+INTERVAL '10 minutes');
 ELSIF p_operation='read_memory_context' THEN
 IF p_args->>'purpose' IS NULL OR p_args->>'purpose' NOT IN ('personalize','suggestion','preference')
 OR jsonb_typeof(p_args->'turn_id') IS DISTINCT FROM 'string'
 OR char_length(p_args->>'turn_id') NOT BETWEEN 1 AND 200
 OR jsonb_typeof(p_args->'mode_id') IS DISTINCT FROM 'string'
 OR (p_args->>'mode_id') !~ '^[a-z][a-z0-9_]{0,31}$'
 OR jsonb_typeof(p_args->'query') IS DISTINCT FROM 'string'
 OR char_length(p_args->>'query')>1000 THEN RAISE EXCEPTION 'Invalid Memory use'; END IF;
 IF NOT s.enabled OR s.use_paused OR p_args->>'mode_id'='reflect'
 OR NOT(SELECT ready FROM public.memory_admission_controls) THEN RETURN '[]'; END IF;
 -- Ownership, scope, state, temporal validity are filters before deterministic lexical ranking.
 SELECT coalesce(jsonb_agg(value ORDER BY rank DESC,memory_id,version),'[]') INTO result FROM (
 SELECT mv.memory_id,mv.version,to_jsonb(mv)||jsonb_build_object('untrusted',TRUE,
 'use_purpose',CASE p_args->>'purpose' WHEN 'personalize' THEN 'Personalize wording using a confirmed fact'
 WHEN 'suggestion' THEN 'Support a relevant suggestion' ELSE 'Use a confirmed preference for the current request' END) value,
 (SELECT count(DISTINCT term) FROM regexp_split_to_table(lower(p_args->>'query'),'[^a-z0-9]+') term
 WHERE term<>'' AND term=ANY(regexp_split_to_array(lower(mv.text),'[^a-z0-9]+'))) rank
 FROM public.memory_versions mv WHERE mv.user_id=p_user_id AND p_args->>'mode_id'=ANY(mv.scopes)
 AND public.memory_effective_state(mv,tz)='active' AND (
 NOT EXISTS(SELECT 1 FROM public.memory_uses WHERE user_id=p_user_id AND turn_id=p_args->>'turn_id')
 OR EXISTS(SELECT 1 FROM public.memory_uses u WHERE u.user_id=p_user_id AND u.turn_id=p_args->>'turn_id'
 AND u.memory_id=mv.memory_id AND u.version=mv.version))
 ) ranked WHERE rank>0 LIMIT 3;
 -- Aggregate LIMIT must apply inside selection; retain only first three records below.
 SELECT coalesce(jsonb_agg(value),'[]') INTO result FROM (SELECT value FROM jsonb_array_elements(result) LIMIT 3) limited;
 INSERT INTO public.memory_uses(user_id,memory_id,version,turn_id,purpose)
 SELECT p_user_id,(x->>'memory_id')::UUID,(x->>'version')::INT,p_args->>'turn_id',p_args->>'purpose'
 FROM jsonb_array_elements(result) x ON CONFLICT DO NOTHING;
 RETURN result;
 END IF;
 IF p_operation IN ('confirm_memory_save','confirm_forget_all_memory') THEN
 SELECT * INTO c FROM public.memory_confirmation_claims WHERE user_id=p_user_id
 AND token_hash=encode(sha256(convert_to(p_args->>'token','UTF8')),'hex') AND consumed_at IS NULL AND expires_at>clock_timestamp();
 IF NOT FOUND THEN RAISE EXCEPTION 'invalid transition: Memory confirmation unavailable'; END IF;
 IF c.settings_version<>s.version THEN RAISE EXCEPTION 'stale version'; END IF;
 END IF;
 IF p_operation='confirm_memory_save' THEN
 IF s.learning_paused OR NOT(SELECT ready FROM public.memory_admission_controls) OR c.operation='forget_all'
 THEN RAISE EXCEPTION 'invalid transition: Memory admission unavailable or learning paused'; END IF;
 v:=public.memory_normalize_payload(p_args->'payload');
 IF public.memory_payload_digest(v)<>c.preview_digest THEN RAISE EXCEPTION 'invalid transition: Memory preview changed'; END IF;
 IF v->>'source_message_id' IS NOT NULL AND NOT EXISTS
 (SELECT 1 FROM public.messages msg JOIN public.sessions ses USING(session_id)
 WHERE msg.message_id=(v->>'source_message_id')::UUID AND msg.user_id=p_user_id
 AND ses.user_id=p_user_id AND ses.mode_id=v->>'source_mode_id') THEN RAISE EXCEPTION 'Memory source unavailable'; END IF;
 IF (v->>'valid_until')::DATE < (clock_timestamp() AT TIME ZONE tz)::DATE THEN RAISE EXCEPTION 'invalid transition: Memory validity date has passed'; END IF;
 IF NOT s.enabled THEN
 IF coalesce((p_args->>'enable_memory')::BOOLEAN,FALSE) IS NOT TRUE OR p_args->>'policy_version' IS DISTINCT FROM 'memory-explicit-v1'
 THEN RAISE EXCEPTION 'invalid transition: Memory opt-in and exact first item required'; END IF;
 IF (SELECT count(*) FROM public.memory_settings WHERE enabled)>=5 THEN RAISE EXCEPTION 'invalid transition: Memory trial admission cap reached'; END IF;
 s.enabled:=TRUE; s.policy_version:='memory-explicit-v1'; s.opted_in_at:=clock_timestamp(); END IF;
 IF c.operation<>'save' THEN
 SELECT * INTO old FROM public.memory_versions WHERE user_id=p_user_id AND memory_id=c.memory_id ORDER BY version DESC LIMIT 1;
 IF NOT FOUND OR old.state IN ('forgotten','superseded') THEN RAISE EXCEPTION 'invalid transition: Memory version unavailable'; END IF;
 IF old.version IS DISTINCT FROM c.memory_version THEN RAISE EXCEPTION 'stale version'; END IF;
 IF c.operation IN ('reconfirm','share') AND (old.text<>v->>'text' OR old.category<>v->>'category') THEN RAISE EXCEPTION 'invalid transition: Memory confirmation changed meaning'; END IF;
 IF c.operation<>'share' AND to_jsonb(old.scopes)<>v->'scopes' THEN RAISE EXCEPTION 'invalid transition: Sharing requires separate preview'; END IF;
 IF c.operation='share' AND old.valid_until IS DISTINCT FROM (v->>'valid_until')::DATE THEN RAISE EXCEPTION 'invalid transition: Sharing cannot change temporal validity'; END IF;
 ELSE IF NOT(v->'scopes' ? (v->>'source_mode_id')) THEN RAISE EXCEPTION 'Origin scope required'; END IF; END IF;
 m.memory_id:=coalesce(old.memory_id,gen_random_uuid()); m.version:=coalesce(old.version,0)+1;
 m.user_id:=p_user_id; m.category:=v->>'category'; m.text:=v->>'text';
 m.source_mode_id:=v->>'source_mode_id'; m.source_channel:=v->>'source_channel';
 m.source_message_id:=(v->>'source_message_id')::UUID; m.source_date:=(v->>'source_date')::DATE;
 m.creation_path:=v->>'creation_path'; SELECT array_agg(value COLLATE "C" ORDER BY value COLLATE "C") INTO m.scopes FROM jsonb_array_elements_text(v->'scopes');
 m.valid_until:=(v->>'valid_until')::DATE; m.goal_state:=coalesce(old.goal_state,'ongoing');
 m.state:=CASE WHEN m.goal_state='ongoing' THEN 'active' ELSE 'inactive' END;
 m.created_at:=clock_timestamp(); m.confirmed_at:=clock_timestamp(); m.supersedes_version:=old.version;
 m.reconfirm_at:=CASE WHEN m.valid_until IS NULL THEN clock_timestamp()+
 CASE WHEN m.category='preference' THEN INTERVAL '180 days' ELSE INTERVAL '90 days' END END;
 IF old.memory_id IS NOT NULL THEN UPDATE public.memory_versions SET state='superseded' WHERE memory_id=old.memory_id AND version=old.version; END IF;
 INSERT INTO public.memory_versions SELECT m.*;
 UPDATE public.memory_confirmation_claims SET consumed_at=clock_timestamp() WHERE token_hash=c.token_hash;
 ELSIF p_operation='disable_memory' THEN
 IF s.version IS DISTINCT FROM (p_args->>'expected_version')::INT THEN RAISE EXCEPTION 'stale version'; END IF;
 DELETE FROM public.memory_uses WHERE user_id=p_user_id;
 DELETE FROM public.memory_versions WHERE user_id=p_user_id;
 DELETE FROM public.memory_confirmation_claims WHERE user_id=p_user_id;
 -- Remove receipts referencing deleted versions and their content-derived hashes.
 DELETE FROM public.memory_command_receipts WHERE user_id=p_user_id;
 s.enabled:=FALSE; s.learning_paused:=FALSE; s.use_paused:=FALSE;
 s.policy_version:=NULL; s.opted_in_at:=NULL;
 ELSIF p_operation='set_memory_pauses' THEN
 IF s.version IS DISTINCT FROM (p_args->>'expected_version')::INT THEN RAISE EXCEPTION 'stale version'; END IF;
 IF coalesce(p_args->>'learning',p_args->>'use') IS NULL THEN RAISE EXCEPTION 'Explicit pause required'; END IF;
 IF p_args->>'learning' IS NOT NULL THEN s.learning_paused:=(p_args->>'learning')::BOOLEAN; END IF;
 IF p_args->>'use' IS NOT NULL THEN s.use_paused:=(p_args->>'use')::BOOLEAN; END IF;
 IF s.learning_paused THEN UPDATE public.memory_confirmation_claims SET consumed_at=clock_timestamp()
 WHERE user_id=p_user_id AND operation<>'forget_all'; END IF;
 ELSIF p_operation IN ('transition_memory','forget_memory') THEN
 SELECT * INTO m FROM public.memory_versions WHERE user_id=p_user_id AND memory_id=(p_args->>'memory_id')::UUID ORDER BY version DESC LIMIT 1;
 IF NOT FOUND THEN RAISE EXCEPTION 'Memory unavailable'; END IF;
 IF m.version IS DISTINCT FROM (p_args->>'expected_version')::INT THEN RAISE EXCEPTION 'stale version'; END IF;
 IF p_operation='transition_memory' THEN
 IF m.state IN ('forgotten','superseded') THEN RAISE EXCEPTION 'invalid transition: Memory unavailable'; END IF;
 action:=p_args->>'action'; old:=m;
 IF action='inactive' THEN m.state:='inactive';
 ELSIF action='use_again' THEN m.state:='active'; IF public.memory_effective_state(m,tz)<>'active' THEN RAISE EXCEPTION 'invalid transition: Memory needs confirmation'; END IF;
 ELSIF action IN ('complete_goal','cancel_goal') AND m.category IN ('goal','project') THEN
 m.state:='inactive'; m.goal_state:=CASE WHEN action='complete_goal' THEN 'completed' ELSE 'cancelled' END;
 ELSE RAISE EXCEPTION 'invalid transition: Invalid Memory action'; END IF;
 m.version:=old.version+1; m.supersedes_version:=old.version;
 UPDATE public.memory_versions SET state='superseded' WHERE memory_id=old.memory_id AND version=old.version;
 INSERT INTO public.memory_versions SELECT m.*;
 ELSE ids:=ARRAY[m.memory_id]; END IF;
 ELSIF p_operation='confirm_forget_all_memory' THEN
 IF c.operation<>'forget_all' OR c.preview_digest<>public.memory_inventory_digest(p_user_id) THEN RAISE EXCEPTION 'invalid transition: Memory inventory changed'; END IF;
 SELECT array_agg(DISTINCT memory_id) INTO ids FROM public.memory_versions WHERE user_id=p_user_id AND state<>'forgotten';
 ELSE RAISE EXCEPTION 'Unknown Memory command'; END IF;
 IF p_operation IN ('forget_memory','confirm_forget_all_memory') THEN
 DELETE FROM public.memory_uses WHERE user_id=p_user_id AND memory_id=ANY(ids);
 UPDATE public.memory_versions SET text=NULL,source_mode_id=NULL,source_channel=NULL,source_message_id=NULL,
 source_date=NULL,creation_path=NULL,scopes='{}',valid_until=NULL,reconfirm_at=NULL,state='forgotten'
 WHERE user_id=p_user_id AND memory_id=ANY(ids);
 -- Even an unrelated outstanding preview can encode the forgotten text in its digest.
 DELETE FROM public.memory_confirmation_claims WHERE user_id=p_user_id;
 UPDATE public.memory_command_receipts SET payload_hash=NULL WHERE user_id=p_user_id;
 result:=CASE WHEN p_operation='forget_memory' THEN jsonb_build_object('status','forgotten','memory_id',m.memory_id)
 ELSE jsonb_build_object('status','forgotten','count',coalesce(cardinality(ids),0)) END;
 END IF;
 s.version:=s.version+1;
 INSERT INTO public.memory_settings SELECT s.* ON CONFLICT(user_id) DO UPDATE SET enabled=EXCLUDED.enabled,
 learning_paused=EXCLUDED.learning_paused,use_paused=EXCLUDED.use_paused,policy_version=EXCLUDED.policy_version,
 opted_in_at=EXCLUDED.opted_in_at,version=EXCLUDED.version;
 IF p_operation='set_memory_pauses' THEN result:=to_jsonb(s);
 ELSIF p_operation='disable_memory' THEN result:=jsonb_build_object('status','disabled','settings',to_jsonb(s));
 ELSIF result IS NULL THEN result:=jsonb_build_object('memory',to_jsonb(m),'settings',to_jsonb(s)); END IF;
 INSERT INTO public.memory_command_receipts(user_id,idempotency_key,payload_hash,operation,memory_id,version,result_metadata)
 VALUES(p_user_id,key,CASE WHEN p_operation IN ('forget_memory','confirm_forget_all_memory') THEN NULL ELSE digest END,
 p_operation,CASE WHEN result ? 'memory' THEN m.memory_id END,
 CASE WHEN result ? 'memory' THEN m.version END,CASE WHEN NOT(result ? 'memory') THEN result END);
 RETURN result;
EXCEPTION WHEN data_exception OR integrity_constraint_violation THEN
 RAISE EXCEPTION 'Invalid Memory input';
END $$;
-- Deliberately preserves superseded/expired history until participant Forget or withdrawal.
-- Only expired or consumed confirmation digests are removed by periodic maintenance.
CREATE FUNCTION public.purge_memory_claims() RETURNS JSONB
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE removed INT; BEGIN
 DELETE FROM public.memory_confirmation_claims
 WHERE consumed_at IS NOT NULL OR expires_at<=clock_timestamp();
 GET DIAGNOSTICS removed = ROW_COUNT;
 RETURN jsonb_build_object('claims',removed);
END $$;
REVOKE ALL ON FUNCTION public.purge_memory_claims() FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.purge_memory_claims() TO service_role;
REVOKE ALL ON FUNCTION public.memory_effective_state(public.memory_versions,TEXT),
 public.memory_normalize_payload(JSONB),public.memory_payload_digest(JSONB),
 public.memory_inventory_digest(UUID),public.memory_command(UUID,TEXT,JSONB) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.memory_command(UUID,TEXT,JSONB) TO service_role;
DO $$ BEGIN
 IF to_regclass('public.memory_admission_controls') IS NULL
 OR to_regclass('public.memory_settings') IS NULL OR to_regclass('public.memory_versions') IS NULL
 OR to_regclass('public.memory_uses') IS NULL OR to_regclass('public.memory_confirmation_claims') IS NULL
 OR to_regclass('public.memory_command_receipts') IS NULL
 OR to_regprocedure('public.memory_command(uuid,text,jsonb)') IS NULL
 OR to_regprocedure('public.memory_payload_digest(jsonb)') IS NULL
 OR to_regprocedure('public.memory_inventory_digest(uuid)') IS NULL
 OR to_regprocedure('public.purge_memory_claims()') IS NULL
 OR NOT EXISTS(SELECT 1 FROM public.memory_admission_controls WHERE singleton AND NOT ready)
 THEN RAISE EXCEPTION '020 objects were not created with admission off'; END IF;
 INSERT INTO public.schema_migrations(version) VALUES(20);
END $$;
COMMIT;
