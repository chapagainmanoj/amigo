-- Channel identities and a primary channel (ADR 0004). Participant identity is user_id; each
-- messaging app links through an opaque (channel, external_id). Telegram stays byte-compatible:
-- telegram_chat_id is kept and mirrored, and the v2 RPCs delegate to the Telegram RPCs for it.
BEGIN;
DO $$ BEGIN
 IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 21) <> 21
 OR (SELECT max(version) FROM public.schema_migrations) <> 21 THEN
 RAISE EXCEPTION '022 requires the complete approved 001-021 chain'; END IF;
END $$;

CREATE TABLE public.channel_identities (
 user_id UUID NOT NULL REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 channel TEXT NOT NULL CHECK (channel ~ '^[a-z][a-z0-9_]{1,31}$'),
 external_id TEXT NOT NULL CHECK (length(external_id) BETWEEN 1 AND 200
   AND external_id = btrim(external_id)),
 linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY (user_id, channel),
 UNIQUE (channel, external_id)
);
ALTER TABLE public.channel_identities ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.channel_identities FROM PUBLIC, anon, authenticated, service_role;
-- Reads only; every write goes through the RPCs and the Telegram mirror trigger below.
GRANT SELECT ON public.channel_identities TO service_role;

INSERT INTO public.channel_identities(user_id, channel, external_id)
 SELECT user_id, 'telegram', telegram_chat_id::TEXT FROM public.user_profiles
 WHERE telegram_chat_id IS NOT NULL
 ON CONFLICT DO NOTHING;

-- Legacy writers (complete_pairing, Store inserts) only set telegram_chat_id. Mirror it so the
-- identity table is complete until 023 retires the column.
CREATE FUNCTION public.mirror_telegram_identity() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$ BEGIN
 IF NEW.telegram_chat_id IS NULL THEN
  DELETE FROM public.channel_identities WHERE user_id = NEW.user_id AND channel = 'telegram';
 ELSE
  INSERT INTO public.channel_identities(user_id, channel, external_id)
   VALUES (NEW.user_id, 'telegram', NEW.telegram_chat_id::TEXT)
  ON CONFLICT (user_id, channel) DO UPDATE SET external_id = EXCLUDED.external_id, linked_at = now();
 END IF;
 RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION public.mirror_telegram_identity() FROM PUBLIC, anon, authenticated, service_role;
CREATE TRIGGER user_profiles_mirror_telegram_identity_insert
 AFTER INSERT ON public.user_profiles
 FOR EACH ROW EXECUTE FUNCTION public.mirror_telegram_identity();
CREATE TRIGGER user_profiles_mirror_telegram_identity_update
 AFTER UPDATE OF telegram_chat_id ON public.user_profiles
 FOR EACH ROW WHEN (OLD.telegram_chat_id IS DISTINCT FROM NEW.telegram_chat_id)
 EXECUTE FUNCTION public.mirror_telegram_identity();

ALTER TABLE public.user_profiles
 ADD COLUMN primary_channel TEXT NOT NULL DEFAULT 'telegram'
   CHECK (primary_channel ~ '^[a-z][a-z0-9_]{1,31}$'),
 ALTER COLUMN telegram_chat_id DROP NOT NULL;
-- Deferred: a new profile and its first identity are written in one transaction, either order.
ALTER TABLE public.user_profiles
 ADD CONSTRAINT user_profiles_primary_channel_linked
 FOREIGN KEY (user_id, primary_channel) REFERENCES public.channel_identities(user_id, channel)
 DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE public.reminders
 ADD COLUMN delivery_channel TEXT CHECK (delivery_channel ~ '^[a-z][a-z0-9_]{1,31}$'),
 ADD COLUMN channel_message_ref TEXT CHECK (length(channel_message_ref) BETWEEN 1 AND 200),
 ADD CONSTRAINT reminders_channel_message_ref_has_channel
   CHECK ((delivery_channel IS NULL) = (channel_message_ref IS NULL));
UPDATE public.reminders
 SET delivery_channel = 'telegram', channel_message_ref = telegram_message_id::TEXT
 WHERE telegram_message_id IS NOT NULL;

-- 015 shape and locks are unchanged. Two decisions change: a signed-in participant whose profile
-- has no Telegram identity yet links Telegram to that profile, and two distinct profiles conflict
-- explicitly instead of through a later unique violation.
CREATE OR REPLACE FUNCTION public.complete_pairing(p_token TEXT, p_telegram_chat_id BIGINT)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_now TIMESTAMPTZ := now();
  v_token public.pairing_tokens%ROWTYPE;
  v_chat_user public.user_profiles%ROWTYPE;
  v_auth_user public.user_profiles%ROWTYPE;
  v_chat_exists BOOLEAN;
  v_auth_exists BOOLEAN;
  v_candidate_user_id UUID;
BEGIN
  SELECT * INTO v_token FROM public.pairing_tokens WHERE token = p_token FOR UPDATE;
  IF NOT FOUND OR v_token.consumed OR v_token.invalidated_at IS NOT NULL
     OR v_token.expires_at <= v_now THEN
    RETURN jsonb_build_object('status', 'invalid_token');
  END IF;

  -- Take both identity candidate locks in an explicit total order, one row per statement.
  FOR v_candidate_user_id IN
    SELECT user_id FROM public.user_profiles
    WHERE telegram_chat_id = p_telegram_chat_id OR supabase_auth_id = v_token.supabase_auth_id
    ORDER BY user_id
  LOOP
    PERFORM 1 FROM public.user_profiles WHERE user_id = v_candidate_user_id FOR UPDATE;
  END LOOP;

  -- Retain the original locked re-reads: a row can enter the predicate after the candidate
  -- snapshot. EvalPlanQual must protect that row before conflict decisions or identity writes.
  SELECT * INTO v_chat_user FROM public.user_profiles
    WHERE telegram_chat_id = p_telegram_chat_id FOR UPDATE;
  v_chat_exists := FOUND;
  SELECT * INTO v_auth_user FROM public.user_profiles
    WHERE supabase_auth_id = v_token.supabase_auth_id FOR UPDATE;
  v_auth_exists := FOUND;

  IF v_chat_exists AND v_auth_exists AND v_chat_user.user_id = v_auth_user.user_id THEN
    UPDATE public.pairing_tokens SET consumed = TRUE, consumed_at = v_now WHERE token = p_token;
    RETURN jsonb_build_object('status', 'already_paired');
  END IF;
  IF (v_chat_exists AND v_auth_exists)
     OR (v_chat_exists AND v_chat_user.supabase_auth_id IS NOT NULL
      AND v_chat_user.supabase_auth_id <> v_token.supabase_auth_id)
     OR (v_auth_exists AND v_auth_user.telegram_chat_id IS NOT NULL
      AND v_auth_user.telegram_chat_id <> p_telegram_chat_id) THEN
    RETURN jsonb_build_object('status', 'conflict');
  END IF;
  IF v_chat_exists THEN
    UPDATE public.user_profiles SET supabase_auth_id = v_token.supabase_auth_id, updated_at = v_now
      WHERE user_id = v_chat_user.user_id RETURNING * INTO v_chat_user;
  ELSIF v_auth_exists THEN
    UPDATE public.user_profiles SET telegram_chat_id = p_telegram_chat_id, updated_at = v_now
      WHERE user_id = v_auth_user.user_id RETURNING * INTO v_chat_user;
  ELSE
    INSERT INTO public.user_profiles(telegram_chat_id, supabase_auth_id)
      VALUES (p_telegram_chat_id, v_token.supabase_auth_id) RETURNING * INTO v_chat_user;
  END IF;
  UPDATE public.pairing_tokens SET consumed = TRUE, consumed_at = v_now WHERE token = p_token;
  RETURN jsonb_build_object('status', 'paired');
EXCEPTION WHEN unique_violation THEN
  RETURN jsonb_build_object('status', 'conflict');
END;
$$;

-- Same statuses as complete_pairing. Telegram delegates so its locks and table stay authoritative.
CREATE FUNCTION public.complete_pairing_v2(p_token TEXT, p_channel TEXT, p_external_id TEXT)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  v_now TIMESTAMPTZ := now();
  v_token public.pairing_tokens%ROWTYPE;
  v_auth_user public.user_profiles%ROWTYPE;
  v_auth_exists BOOLEAN;
  v_owner_id UUID;
  v_candidate_user_id UUID;
BEGIN
  IF p_channel IS NULL OR p_channel !~ '^[a-z][a-z0-9_]{1,31}$'
     OR p_external_id IS NULL OR length(p_external_id) NOT BETWEEN 1 AND 200
     OR p_external_id <> btrim(p_external_id) THEN
    RAISE EXCEPTION 'invalid_channel_identity';
  END IF;
  IF p_channel = 'telegram' THEN
    IF p_external_id !~ '^-?[1-9][0-9]{0,17}$' THEN RAISE EXCEPTION 'invalid_channel_identity'; END IF;
    RETURN public.complete_pairing(p_token, p_external_id::BIGINT);
  END IF;

  SELECT * INTO v_token FROM public.pairing_tokens WHERE token = p_token FOR UPDATE;
  IF NOT FOUND OR v_token.consumed OR v_token.invalidated_at IS NOT NULL
     OR v_token.expires_at <= v_now THEN
    RETURN jsonb_build_object('status', 'invalid_token');
  END IF;

  FOR v_candidate_user_id IN
    SELECT user_id FROM public.user_profiles
    WHERE supabase_auth_id = v_token.supabase_auth_id
       OR user_id IN (SELECT ci.user_id FROM public.channel_identities ci
                      WHERE ci.channel = p_channel AND ci.external_id = p_external_id)
    ORDER BY user_id
  LOOP
    PERFORM 1 FROM public.user_profiles WHERE user_id = v_candidate_user_id FOR UPDATE;
  END LOOP;

  SELECT ci.user_id INTO v_owner_id FROM public.channel_identities ci
    WHERE ci.channel = p_channel AND ci.external_id = p_external_id FOR UPDATE;
  SELECT * INTO v_auth_user FROM public.user_profiles
    WHERE supabase_auth_id = v_token.supabase_auth_id FOR UPDATE;
  v_auth_exists := FOUND;

  IF v_owner_id IS NOT NULL AND v_auth_exists AND v_owner_id = v_auth_user.user_id THEN
    UPDATE public.pairing_tokens SET consumed = TRUE, consumed_at = v_now WHERE token = p_token;
    RETURN jsonb_build_object('status', 'already_paired');
  END IF;
  IF v_owner_id IS NOT NULL
     OR (v_auth_exists AND EXISTS (SELECT 1 FROM public.channel_identities ci
         WHERE ci.user_id = v_auth_user.user_id AND ci.channel = p_channel)) THEN
    RETURN jsonb_build_object('status', 'conflict');
  END IF;
  IF v_auth_exists THEN
    UPDATE public.user_profiles SET updated_at = v_now WHERE user_id = v_auth_user.user_id;
  ELSE
    INSERT INTO public.user_profiles(supabase_auth_id, primary_channel)
      VALUES (v_token.supabase_auth_id, p_channel) RETURNING * INTO v_auth_user;
  END IF;
  INSERT INTO public.channel_identities(user_id, channel, external_id)
    VALUES (v_auth_user.user_id, p_channel, p_external_id);
  UPDATE public.pairing_tokens SET consumed = TRUE, consumed_at = v_now WHERE token = p_token;
  RETURN jsonb_build_object('status', 'paired');
EXCEPTION WHEN unique_violation THEN
  RETURN jsonb_build_object('status', 'conflict');
END;
$$;

CREATE FUNCTION public.set_primary_channel(p_user_id UUID, p_channel TEXT)
RETURNS TEXT LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$ BEGIN
 PERFORM 1 FROM public.user_profiles WHERE user_id = p_user_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'user_not_found'; END IF;
 IF NOT EXISTS (SELECT 1 FROM public.channel_identities
                WHERE user_id = p_user_id AND channel = p_channel) THEN
  RAISE EXCEPTION 'channel_not_linked';
 END IF;
 UPDATE public.user_profiles SET primary_channel = p_channel, updated_at = now()
  WHERE user_id = p_user_id;
 RETURN p_channel;
END $$;

-- 011 behaviour plus a channel-neutral message reference. Telegram also writes
-- telegram_message_id, which the 013 Activation delivery predicate still reads.
CREATE FUNCTION public.finish_reminder_delivery_v2(
  p_attempt_id UUID,
  p_reminder_id UUID,
  p_user_id UUID,
  p_result public.reminder_attempt_result,
  p_normalized_cause TEXT,
  p_retry_decision public.reminder_retry_decision,
  p_channel TEXT,
  p_channel_message_ref TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  attempt_row public.reminder_delivery_attempts%ROWTYPE;
  finished_time TIMESTAMPTZ := now();
BEGIN
  IF p_result IS NULL OR p_retry_decision IS NULL THEN
    RAISE EXCEPTION 'invalid_delivery_outcome';
  END IF;
  IF p_retry_decision = 'unknown'
    OR (p_result = 'accepted' AND p_retry_decision <> 'do_not_retry')
    OR (
      p_result <> 'accepted'
      AND btrim(COALESCE(p_normalized_cause, '')) = ''
    )
  THEN
    RAISE EXCEPTION 'invalid_delivery_outcome';
  END IF;
  IF p_channel IS NULL OR p_channel !~ '^[a-z][a-z0-9_]{1,31}$' THEN
    RAISE EXCEPTION 'invalid_delivery_channel';
  END IF;
  IF p_result = 'accepted' AND (
    p_channel_message_ref IS NULL OR length(p_channel_message_ref) NOT BETWEEN 1 AND 200
    OR (p_channel = 'telegram' AND p_channel_message_ref !~ '^[1-9][0-9]{0,17}$')
  ) THEN
    RAISE EXCEPTION 'accepted_delivery_requires_message_id';
  END IF;

  UPDATE public.reminder_delivery_attempts AS attempt
  SET
    finished_at = finished_time,
    provider_accepted_at = CASE WHEN p_result = 'accepted' THEN finished_time ELSE NULL END,
    result = p_result,
    normalized_cause = CASE
      WHEN p_normalized_cause IS NULL THEN NULL ELSE left(p_normalized_cause, 100)
    END,
    retry_decision = p_retry_decision,
    provider_latency_ms = GREATEST(
      0,
      round(extract(epoch FROM (finished_time - attempt.started_at)) * 1000)::BIGINT
    )
  WHERE attempt.attempt_id = p_attempt_id
    AND attempt.user_id = p_user_id
    AND attempt.finished_at IS NULL
    AND EXISTS (
      SELECT 1
      FROM public.reminder_occurrences AS occurrence
      WHERE occurrence.occurrence_id = attempt.occurrence_id
        AND occurrence.reminder_id = p_reminder_id
        AND occurrence.user_id = p_user_id
    )
  RETURNING * INTO attempt_row;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'delivery_attempt_not_found_or_finished';
  END IF;

  UPDATE public.reminders AS reminder
  SET
    status = CASE
      WHEN p_result = 'accepted' THEN 'sent'::public.reminder_status
      WHEN p_retry_decision = 'retry' THEN 'pending'::public.reminder_status
      ELSE 'failed'::public.reminder_status
    END,
    telegram_message_id = CASE
      WHEN p_result <> 'accepted' THEN reminder.telegram_message_id
      WHEN p_channel = 'telegram' THEN p_channel_message_ref::BIGINT
      ELSE NULL
    END,
    delivery_channel = CASE
      WHEN p_result = 'accepted' THEN p_channel ELSE reminder.delivery_channel
    END,
    channel_message_ref = CASE
      WHEN p_result = 'accepted' THEN p_channel_message_ref ELSE reminder.channel_message_ref
    END
  WHERE reminder.reminder_id = p_reminder_id
    AND reminder.user_id = p_user_id
    AND reminder.status = 'sending';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'reminder_delivery_state_conflict';
  END IF;

  RETURN jsonb_build_object('attempt', to_jsonb(attempt_row));
END;
$$;

-- Current code still calls v1. Route it through v2 so Reminders delivered during the transition
-- also record delivery_channel and channel_message_ref; signature, ACL and errors are unchanged.
CREATE OR REPLACE FUNCTION public.finish_reminder_delivery(
  p_attempt_id UUID,
  p_reminder_id UUID,
  p_user_id UUID,
  p_result public.reminder_attempt_result,
  p_normalized_cause TEXT,
  p_retry_decision public.reminder_retry_decision,
  p_telegram_message_id BIGINT
)
RETURNS JSONB
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT public.finish_reminder_delivery_v2(p_attempt_id, p_reminder_id, p_user_id, p_result,
    p_normalized_cause, p_retry_decision, 'telegram', p_telegram_message_id::TEXT);
$$;

-- Update claims for channels other than Telegram. Telegram keeps telegram_update_claims so a
-- redelivery claimed before this deploy is still recognised after it.
CREATE TABLE public.channel_update_claims (
  channel TEXT NOT NULL CHECK (channel ~ '^[a-z][a-z0-9_]{1,31}$' AND channel <> 'telegram'),
  update_id TEXT NOT NULL CHECK (length(update_id) BETWEEN 1 AND 200),
  external_id TEXT NOT NULL CHECK (length(external_id) BETWEEN 1 AND 200),
  update_kind TEXT NOT NULL CHECK (update_kind IN ('message', 'callback_query')),
  status TEXT NOT NULL DEFAULT 'processing' CHECK (
    status IN ('processing', 'completed', 'failed')
  ),
  failure_code TEXT CHECK (
    failure_code IS NULL OR length(failure_code) BETWEEN 1 AND 100
  ),
  claimed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  PRIMARY KEY (channel, update_id),
  CHECK (
    (status = 'processing' AND finished_at IS NULL AND failure_code IS NULL)
    OR (status = 'completed' AND finished_at IS NOT NULL AND failure_code IS NULL)
    OR (status = 'failed' AND finished_at IS NOT NULL AND failure_code IS NOT NULL)
  )
);
CREATE INDEX idx_channel_update_claims_claimed_at ON public.channel_update_claims(claimed_at);
CREATE INDEX idx_channel_update_claims_unfinished
  ON public.channel_update_claims(claimed_at) WHERE status = 'processing';
ALTER TABLE public.channel_update_claims ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.channel_update_claims FROM PUBLIC, anon, authenticated, service_role;

CREATE FUNCTION public._channel_update_json(p_claimed BOOLEAN, p_row public.channel_update_claims)
RETURNS JSONB LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT jsonb_strip_nulls(jsonb_build_object('claimed', p_claimed))
    || jsonb_build_object(
      'channel', p_row.channel, 'update_id', p_row.update_id, 'external_id', p_row.external_id,
      'update_kind', p_row.update_kind, 'status', p_row.status,
      'failure_code', p_row.failure_code, 'claimed_at', p_row.claimed_at,
      'finished_at', p_row.finished_at);
$$;
REVOKE ALL ON FUNCTION public._channel_update_json(BOOLEAN, public.channel_update_claims)
  FROM PUBLIC, anon, authenticated, service_role;

-- Telegram results are reshaped to the channel-neutral keys; ids become text.
CREATE FUNCTION public._telegram_update_as_channel(p_result JSONB) RETURNS JSONB
LANGUAGE sql IMMUTABLE SET search_path = '' AS $$
  SELECT (p_result - 'telegram_chat_id' - 'update_id') || jsonb_build_object(
    'channel', 'telegram', 'update_id', p_result->>'update_id',
    'external_id', p_result->>'telegram_chat_id');
$$;
REVOKE ALL ON FUNCTION public._telegram_update_as_channel(JSONB)
  FROM PUBLIC, anon, authenticated, service_role;

CREATE FUNCTION public.claim_channel_update(
  p_channel TEXT, p_update_id TEXT, p_external_id TEXT, p_update_kind TEXT
)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE claimed_update public.channel_update_claims%ROWTYPE;
BEGIN
  IF p_channel = 'telegram' THEN
    IF p_update_id !~ '^(0|[1-9][0-9]{0,17})$' OR p_external_id !~ '^-?[1-9][0-9]{0,17}$' THEN
      RAISE EXCEPTION 'invalid_channel_update';
    END IF;
    RETURN public._telegram_update_as_channel(public.claim_telegram_update(
      p_update_id::BIGINT, p_external_id::BIGINT, p_update_kind));
  END IF;
  IF p_channel IS NULL OR p_channel !~ '^[a-z][a-z0-9_]{1,31}$'
     OR p_update_id IS NULL OR length(p_update_id) NOT BETWEEN 1 AND 200
     OR p_external_id IS NULL OR length(p_external_id) NOT BETWEEN 1 AND 200 THEN
    RAISE EXCEPTION 'invalid_channel_update';
  END IF;
  IF p_update_kind IS NULL OR p_update_kind NOT IN ('message', 'callback_query') THEN
    RAISE EXCEPTION 'invalid_channel_update_kind';
  END IF;

  INSERT INTO public.channel_update_claims(channel, update_id, external_id, update_kind)
    VALUES (p_channel, p_update_id, p_external_id, p_update_kind)
  ON CONFLICT (channel, update_id) DO NOTHING
  RETURNING * INTO claimed_update;
  IF FOUND THEN
    RETURN public._channel_update_json(TRUE, claimed_update);
  END IF;

  SELECT claim.* INTO claimed_update FROM public.channel_update_claims AS claim
    WHERE claim.channel = p_channel AND claim.update_id = p_update_id;
  IF claimed_update.external_id <> p_external_id OR claimed_update.update_kind <> p_update_kind THEN
    RAISE EXCEPTION 'channel_update_identity_conflict';
  END IF;
  RETURN public._channel_update_json(FALSE, claimed_update);
END;
$$;

CREATE FUNCTION public.finish_channel_update(
  p_channel TEXT, p_update_id TEXT, p_status TEXT, p_failure_code TEXT DEFAULT NULL
)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE finished_update public.channel_update_claims%ROWTYPE;
BEGIN
  IF p_channel = 'telegram' THEN
    IF p_update_id !~ '^(0|[1-9][0-9]{0,17})$' THEN RAISE EXCEPTION 'invalid_channel_update'; END IF;
    RETURN public._telegram_update_as_channel(public.finish_telegram_update(
      p_update_id::BIGINT, p_status, p_failure_code));
  END IF;
  IF p_channel IS NULL OR p_channel !~ '^[a-z][a-z0-9_]{1,31}$'
     OR p_update_id IS NULL OR length(p_update_id) NOT BETWEEN 1 AND 200 THEN
    RAISE EXCEPTION 'invalid_channel_update';
  END IF;
  IF p_status IS NULL OR p_status NOT IN ('completed', 'failed') THEN
    RAISE EXCEPTION 'invalid_channel_update_status';
  END IF;
  IF (p_status = 'completed' AND p_failure_code IS NOT NULL)
    OR (p_status = 'failed' AND (
      p_failure_code IS NULL OR length(p_failure_code) NOT BETWEEN 1 AND 100
    ))
  THEN
    RAISE EXCEPTION 'invalid_channel_failure_code';
  END IF;

  UPDATE public.channel_update_claims AS claim
  SET status = p_status, failure_code = p_failure_code, finished_at = now()
  WHERE claim.channel = p_channel AND claim.update_id = p_update_id
    AND claim.status = 'processing'
  RETURNING * INTO finished_update;
  IF NOT FOUND THEN
    SELECT claim.* INTO finished_update FROM public.channel_update_claims AS claim
      WHERE claim.channel = p_channel AND claim.update_id = p_update_id;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'channel_update_not_found';
    END IF;
    IF finished_update.status <> p_status
      OR finished_update.failure_code IS DISTINCT FROM p_failure_code
    THEN
      RAISE EXCEPTION 'channel_update_already_finished';
    END IF;
  END IF;
  RETURN public._channel_update_json(NULL, finished_update);
END;
$$;

DO $$ DECLARE fn RECORD; BEGIN
 FOR fn IN SELECT unnest(ARRAY[
   'public.complete_pairing_v2(text,text,text)',
   'public.set_primary_channel(uuid,text)',
   'public.finish_reminder_delivery_v2(uuid,uuid,uuid,public.reminder_attempt_result,text,public.reminder_retry_decision,text,text)',
   'public.claim_channel_update(text,text,text,text)',
   'public.finish_channel_update(text,text,text,text)']) AS signature
 LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated', fn.signature);
  EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role', fn.signature);
 END LOOP;
END $$;

DO $$ DECLARE v_definition TEXT; BEGIN
 IF to_regclass('public.channel_identities') IS NULL
  OR to_regclass('public.channel_update_claims') IS NULL
  OR NOT (SELECT relrowsecurity FROM pg_catalog.pg_class WHERE oid='public.channel_identities'::regclass)
  OR NOT (SELECT relrowsecurity FROM pg_catalog.pg_class WHERE oid='public.channel_update_claims'::regclass)
  OR has_table_privilege('service_role', 'public.channel_identities', 'INSERT')
  OR to_regprocedure('public.complete_pairing_v2(text,text,text)') IS NULL
  OR to_regprocedure('public.claim_channel_update(text,text,text,text)') IS NULL
 THEN RAISE EXCEPTION '022 objects were not created'; END IF;
 IF (SELECT count(*) FROM public.user_profiles WHERE telegram_chat_id IS NOT NULL)
  <> (SELECT count(*) FROM public.channel_identities WHERE channel = 'telegram')
 THEN RAISE EXCEPTION '022 Telegram identity backfill is incomplete'; END IF;
 SELECT lower(regexp_replace(regexp_replace(
   pg_get_functiondef('public.complete_pairing(text,bigint)'::regprocedure),
   '--[^\n]*', '', 'g'), '\s+', ' ', 'g')) INTO v_definition;
 IF v_definition !~ 'order by user_id loop perform 1 from public.user_profiles'
  OR v_definition !~ 'where user_id = v_candidate_user_id for update'
  OR v_definition !~ 'where telegram_chat_id = p_telegram_chat_id for update'
  OR v_definition !~ 'where supabase_auth_id = v_token.supabase_auth_id for update' THEN
  RAISE EXCEPTION '022 lost the 015 ordered locks and locked re-reads';
 END IF;
 INSERT INTO public.schema_migrations(version) VALUES(22);
END $$;
COMMIT;
