BEGIN;
DO $$ BEGIN
 IF (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 18) <> 18
    OR (SELECT max(version) FROM public.schema_migrations) <> 18 THEN
   RAISE EXCEPTION '019 requires the complete approved 001-018 chain'; END IF;
END $$;

CREATE TABLE public.proactive_reservations (
 user_id UUID NOT NULL REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 delivery_key TEXT NOT NULL CHECK (length(delivery_key) BETWEEN 1 AND 250),
 kind TEXT NOT NULL CHECK (kind IN ('reminder','recovery','coaching')),
 program_id UUID REFERENCES public.coaching_programs(program_id) ON DELETE SET NULL,
 scheduled_at TIMESTAMPTZ NOT NULL, timezone TEXT NOT NULL, local_day DATE NOT NULL,
 state TEXT NOT NULL DEFAULT 'reserved'
   CHECK (state IN ('reserved','dispatched','accepted','rejected','uncertain','cancelled')),
 legacy_debt BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(user_id,delivery_key)
);
CREATE INDEX proactive_budget_day ON public.proactive_reservations(user_id,local_day);
CREATE TABLE public.proactive_processing_consents (
 user_id UUID NOT NULL REFERENCES public.user_profiles(user_id) ON DELETE CASCADE,
 scope TEXT NOT NULL CHECK (scope IN ('coaching-v1','reflect-v1')),
 policy_version TEXT CHECK (policy_version IS NULL OR length(btrim(policy_version))>0),
 country_code TEXT CHECK(country_code IS NULL OR country_code ~ '^[A-Z]{2}$'),
 acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT now(), withdrawn_at TIMESTAMPTZ,
 PRIMARY KEY(user_id,scope)
);
CREATE TABLE public.coaching_delivery_replies (
 user_id UUID NOT NULL, program_id UUID NOT NULL,
 last_reply_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(user_id,program_id),
 FOREIGN KEY(program_id,user_id) REFERENCES public.coaching_programs(program_id,user_id)
   ON DELETE CASCADE
);
CREATE TABLE public.coaching_delivery_outbox (
 user_id UUID NOT NULL, delivery_key TEXT NOT NULL,
 program_id UUID NOT NULL, program_version BIGINT NOT NULL,
 local_day DATE NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('check_in','follow_up','weekly_review')),
 scheduled_at TIMESTAMPTZ NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending'
   CHECK (state IN ('pending','claimed','dispatched','accepted','rejected','uncertain','cancelled')),
 claim_token UUID, claimed_at TIMESTAMPTZ, worker_id TEXT,
 dispatched_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
 PRIMARY KEY(user_id,delivery_key), UNIQUE(program_id,local_day),
 FOREIGN KEY(user_id,delivery_key) REFERENCES public.proactive_reservations(user_id,delivery_key)
   ON DELETE CASCADE,
 FOREIGN KEY(program_id,user_id) REFERENCES public.coaching_programs(program_id,user_id)
   ON DELETE CASCADE
);
CREATE INDEX coaching_delivery_due ON public.coaching_delivery_outbox(scheduled_at)
 WHERE state IN ('pending','claimed','dispatched');
ALTER TABLE public.proactive_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.proactive_processing_consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coaching_delivery_replies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coaching_delivery_outbox ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.proactive_reservations,public.proactive_processing_consents,
 public.coaching_delivery_replies,public.coaching_delivery_outbox
 FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.proactive_reservations,public.proactive_processing_consents,
 public.coaching_delivery_replies,public.coaching_delivery_outbox TO service_role;

-- Lock order: owned program (where applicable), per-participant budget, outbox row.
-- No caller supplies a limit. The profile's existing daily_message_budget is authoritative.
CREATE FUNCTION public.reserve_proactive_delivery(
 p_user_id UUID,p_delivery_key TEXT,p_kind TEXT,p_scheduled_at TIMESTAMPTZ,
 p_program_id UUID DEFAULT NULL
) RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE u public.user_profiles%ROWTYPE; r public.proactive_reservations%ROWTYPE;
 zone TEXT; day DATE; used BIGINT; BEGIN
 IF p_delivery_key IS NULL OR length(p_delivery_key) NOT BETWEEN 1 AND 250
    OR p_kind IS NULL OR p_kind NOT IN ('reminder','recovery','coaching') OR p_scheduled_at IS NULL
 THEN RAISE EXCEPTION 'invalid_proactive_reservation'; END IF;
 SELECT * INTO u FROM public.user_profiles WHERE user_id=p_user_id FOR KEY SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'proactive_owner_unavailable'; END IF;
 IF p_program_id IS NOT NULL THEN
   PERFORM 1 FROM public.coaching_programs WHERE program_id=p_program_id AND user_id=p_user_id
     FOR KEY SHARE;
   IF NOT FOUND THEN RAISE EXCEPTION 'coaching_owner_unavailable'; END IF;
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-proactive:'||p_user_id,0));
 zone:=coalesce(u.timezone,'UTC'); day:=(p_scheduled_at AT TIME ZONE zone)::date;
 SELECT * INTO r FROM public.proactive_reservations
 WHERE user_id=p_user_id AND delivery_key=p_delivery_key FOR UPDATE;
 IF FOUND AND r.state<>'cancelled' THEN
   IF r.kind<>p_kind OR r.scheduled_at<>p_scheduled_at
      OR r.program_id IS DISTINCT FROM p_program_id THEN
     RAISE EXCEPTION 'proactive_key_conflict'; END IF;
   RETURN jsonb_build_object('status','already_reserved','reservation',to_jsonb(r));
 END IF;
 SELECT count(*) INTO used FROM public.proactive_reservations
 WHERE user_id=p_user_id AND state<>'cancelled' AND
   (local_day=day OR (scheduled_at AT TIME ZONE zone)::date=day);
 IF used >= greatest(0,coalesce(u.daily_message_budget,4))
    OR (p_kind='coaching' AND EXISTS(SELECT 1 FROM public.proactive_reservations
      WHERE user_id=p_user_id AND kind='coaching' AND state<>'cancelled'
      AND (local_day=day OR (scheduled_at AT TIME ZONE zone)::date=day))) THEN
   RETURN jsonb_build_object('status','budget_exhausted'); END IF;
 IF p_program_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM public.coaching_programs
   WHERE program_id=p_program_id AND user_id=p_user_id) THEN
   RAISE EXCEPTION 'coaching_owner_unavailable'; END IF;
 INSERT INTO public.proactive_reservations(user_id,delivery_key,kind,program_id,
   scheduled_at,timezone,local_day) VALUES(p_user_id,p_delivery_key,p_kind,p_program_id,
   p_scheduled_at,zone,day) ON CONFLICT(user_id,delivery_key) DO UPDATE
   SET kind=EXCLUDED.kind,program_id=EXCLUDED.program_id,scheduled_at=EXCLUDED.scheduled_at,
       timezone=EXCLUDED.timezone,local_day=EXCLUDED.local_day,state='reserved',legacy_debt=FALSE
   RETURNING * INTO r;
 RETURN jsonb_build_object('status','reserved','reservation',to_jsonb(r));
END $$;
CREATE FUNCTION public.release_proactive_delivery(p_user_id UUID,p_delivery_key TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-proactive:'||p_user_id,0));
 UPDATE public.proactive_reservations SET state='cancelled'
 WHERE user_id=p_user_id AND delivery_key=p_delivery_key AND state='reserved';
 RETURN FOUND;
END $$;

-- Reminder inserts share the same atomic admission ledger, including Later and dashboard writes.
-- A refusal rolls back the complete calling command (prior cancellation, outbox and receipt).
CREATE FUNCTION public.reserve_reminder_budget() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE result JSONB; BEGIN
 result:=public.reserve_proactive_delivery(NEW.user_id,'reminder:'||NEW.reminder_id,
   'reminder',NEW.scheduled_time,NULL);
 IF result->>'status'='budget_exhausted' THEN
   RAISE EXCEPTION 'proactive_budget_exhausted'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER reminder_budget_admission BEFORE INSERT ON public.reminders
 FOR EACH ROW EXECUTE FUNCTION public.reserve_reminder_budget();
CREATE FUNCTION public.update_reminder_budget() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN
 IF NEW.scheduled_time IS DISTINCT FROM OLD.scheduled_time
    OR NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.task_id IS DISTINCT FROM OLD.task_id
    OR NEW.reminder_id IS DISTINCT FROM OLD.reminder_id THEN
   RAISE EXCEPTION 'immutable_reminder_schedule'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(
   pg_catalog.hashtextextended('amigo-proactive:'||NEW.user_id,0));
 IF NEW.status='sending' THEN
   UPDATE public.proactive_reservations SET state='dispatched'
    WHERE user_id=NEW.user_id AND delivery_key='reminder:'||NEW.reminder_id
      AND state='reserved';
 ELSIF NEW.status='sent' THEN
   UPDATE public.proactive_reservations SET state='accepted'
    WHERE user_id=NEW.user_id AND delivery_key='reminder:'||NEW.reminder_id;
 ELSIF NEW.status IN ('cancelled','acknowledged','missed','failed') THEN
   -- Unsent cancellations free a slot. Attempted delivery remains counted conservatively.
   UPDATE public.proactive_reservations SET state='cancelled'
    WHERE user_id=NEW.user_id AND delivery_key='reminder:'||NEW.reminder_id
      AND state='reserved';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER reminder_budget_status BEFORE UPDATE OF status,scheduled_time,user_id,task_id,reminder_id
 ON public.reminders FOR EACH ROW
 EXECUTE FUNCTION public.update_reminder_budget();
REVOKE ALL ON FUNCTION public.reserve_reminder_budget(),public.update_reminder_budget()
 FROM PUBLIC,anon,authenticated,service_role;

-- Existing commitments consume capacity first. Overflow remains visible as legacy debt;
-- no existing Reminder is dropped or declared compliant with the new cap retroactively.
WITH commitments AS (
 SELECT r.user_id,'reminder:'||r.reminder_id delivery_key,r.scheduled_time scheduled_at,
   coalesce(u.timezone,'UTC') zone,greatest(0,coalesce(u.daily_message_budget,4)) budget,
   CASE WHEN r.status='sent' OR r.telegram_message_id IS NOT NULL THEN 'accepted'
     WHEN r.status='sending' OR EXISTS(SELECT 1 FROM public.reminder_occurrences o
       WHERE o.reminder_id=r.reminder_id AND o.first_claimed_at IS NOT NULL) THEN 'uncertain'
     ELSE 'reserved' END reservation_state,
   row_number() OVER(PARTITION BY r.user_id,
     (r.scheduled_time AT TIME ZONE coalesce(u.timezone,'UTC'))::date
     ORDER BY r.scheduled_time,r.reminder_id) ordinal
 FROM public.reminders r JOIN public.user_profiles u ON u.user_id=r.user_id
 WHERE r.status IN ('pending','sending','sent') OR r.telegram_message_id IS NOT NULL
   OR EXISTS(SELECT 1 FROM public.reminder_occurrences o WHERE o.reminder_id=r.reminder_id
     AND o.first_claimed_at IS NOT NULL)
) INSERT INTO public.proactive_reservations(user_id,delivery_key,kind,scheduled_at,
 timezone,local_day,legacy_debt,state)
 SELECT user_id,delivery_key,'reminder',scheduled_at,zone,
   (scheduled_at AT TIME ZONE zone)::date,ordinal>budget,reservation_state FROM commitments;

CREATE FUNCTION public.get_proactive_consent(p_user_id UUID,p_scope TEXT)
RETURNS JSONB LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT to_jsonb(c) FROM public.proactive_processing_consents c
 WHERE user_id=p_user_id AND scope=p_scope;
$$;
CREATE FUNCTION public.set_proactive_consent(p_user_id UUID,p_scope TEXT,p_policy_version TEXT,
 p_country_code TEXT DEFAULT NULL,p_withdraw BOOLEAN DEFAULT FALSE)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE r public.proactive_processing_consents%ROWTYPE; BEGIN
 IF p_scope IS NULL OR p_scope NOT IN ('coaching-v1','reflect-v1') OR p_withdraw IS NULL
 OR (NOT p_withdraw AND (p_policy_version IS NULL OR length(btrim(p_policy_version))=0))
 OR (p_country_code IS NOT NULL AND upper(p_country_code) !~ '^[A-Z]{2}$') THEN
   RAISE EXCEPTION 'approved_processing_policy_required'; END IF;
 PERFORM 1 FROM public.user_profiles WHERE user_id=p_user_id FOR KEY SHARE;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-proactive:'||p_user_id,0));
 INSERT INTO public.proactive_processing_consents(user_id,scope,policy_version,country_code,withdrawn_at)
 VALUES(p_user_id,p_scope,p_policy_version,upper(p_country_code),
   CASE WHEN p_withdraw THEN clock_timestamp() END)
 ON CONFLICT(user_id,scope) DO UPDATE
 SET policy_version=coalesce(EXCLUDED.policy_version,public.proactive_processing_consents.policy_version),
 country_code=coalesce(EXCLUDED.country_code,public.proactive_processing_consents.country_code),
 acknowledged_at=clock_timestamp(),withdrawn_at=EXCLUDED.withdrawn_at RETURNING * INTO r;
 IF p_withdraw AND p_scope='coaching-v1' THEN
   UPDATE public.coaching_delivery_outbox SET state='cancelled',finished_at=clock_timestamp()
    WHERE user_id=p_user_id AND state IN ('pending','claimed');
   UPDATE public.proactive_reservations SET state='cancelled'
    WHERE user_id=p_user_id AND kind='coaching' AND state='reserved';
 END IF;
 RETURN to_jsonb(r);
END $$;
CREATE FUNCTION public.set_coaching_consent(p_user_id UUID,p_policy_version TEXT DEFAULT NULL)
RETURNS JSONB LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT public.set_proactive_consent(p_user_id,'coaching-v1',p_policy_version,NULL,p_policy_version IS NULL);
$$;
CREATE FUNCTION public.has_coaching_consent(p_user_id UUID) RETURNS BOOLEAN
LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(SELECT 1 FROM public.proactive_processing_consents WHERE user_id=p_user_id
   AND scope='coaching-v1' AND policy_version='coaching-v1' AND withdrawn_at IS NULL);
$$;
CREATE FUNCTION public.note_coaching_reply(p_user_id UUID,p_program_id UUID) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.coaching_programs WHERE program_id=p_program_id AND user_id=p_user_id)
 THEN RETURN FALSE; END IF;
 INSERT INTO public.coaching_delivery_replies(user_id,program_id,last_reply_at)
 VALUES(p_user_id,p_program_id,clock_timestamp()) ON CONFLICT(user_id,program_id)
 DO UPDATE SET last_reply_at=EXCLUDED.last_reply_at; RETURN TRUE;
END $$;
CREATE FUNCTION public.get_coaching_delivery_history(p_user_id UUID,p_program_id UUID)
RETURNS JSONB LANGUAGE sql SECURITY DEFINER SET search_path='' AS $$
 SELECT jsonb_build_object('last_reply_at',(SELECT last_reply_at FROM public.coaching_delivery_replies
 WHERE user_id=p_user_id AND program_id=p_program_id),'deliveries',coalesce((SELECT jsonb_agg(to_jsonb(d)
 ORDER BY scheduled_at) FROM public.coaching_delivery_outbox d WHERE user_id=p_user_id
 AND program_id=p_program_id),'[]'::jsonb));
$$;
CREATE FUNCTION public.enqueue_coaching_delivery(p_user_id UUID,p_program_id UUID,
 p_expected_version BIGINT,p_delivery_key TEXT,p_local_day DATE,p_kind TEXT,p_scheduled_at TIMESTAMPTZ)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE p public.coaching_programs%ROWTYPE; d public.coaching_delivery_outbox%ROWTYPE; r JSONB; auth UUID; BEGIN
 SELECT supabase_auth_id INTO auth FROM public.user_profiles WHERE user_id=p_user_id;
 IF auth IS NULL OR coalesce((public.get_activation_state(auth)->>'completed')::boolean,FALSE) IS NOT TRUE THEN
   RETURN jsonb_build_object('status','unavailable'); END IF;
 SELECT * INTO p FROM public.coaching_programs WHERE program_id=p_program_id AND user_id=p_user_id FOR UPDATE;
 IF NOT FOUND OR p.state<>'active' OR p.version<>p_expected_version
    OR clock_timestamp()<p.starts_at OR clock_timestamp()>=p.ends_at
    OR NOT public.has_coaching_consent(p_user_id) OR NOT EXISTS(SELECT 1 FROM public.mode_grants
      WHERE user_id=p_user_id AND mode_id='coach' AND revoked_at IS NULL AND expires_at>clock_timestamp())
 THEN RETURN jsonb_build_object('status','unavailable'); END IF;
 IF p_kind IS NULL OR p_kind NOT IN ('check_in','follow_up','weekly_review') OR p_local_day IS NULL
    OR p_local_day<>(p_scheduled_at AT TIME ZONE p.timezone)::date THEN
   RETURN jsonb_build_object('status','invalid'); END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-proactive:'||p_user_id,0));
 SELECT * INTO d FROM public.coaching_delivery_outbox WHERE program_id=p_program_id AND local_day=p_local_day;
 IF FOUND THEN RETURN jsonb_build_object('status','already_queued','delivery',to_jsonb(d)); END IF;
 r:=public.reserve_proactive_delivery(p_user_id,p_delivery_key,'coaching',p_scheduled_at,p_program_id);
 IF r->>'status'='budget_exhausted' THEN RETURN r; END IF;
 INSERT INTO public.coaching_delivery_outbox(user_id,delivery_key,program_id,program_version,
 local_day,kind,scheduled_at) VALUES(p_user_id,p_delivery_key,p_program_id,p_expected_version,
 p_local_day,p_kind,p_scheduled_at) RETURNING * INTO d;
 RETURN jsonb_build_object('status','queued','delivery',to_jsonb(d));
END $$;
CREATE FUNCTION public.claim_coaching_deliveries(p_worker_id TEXT,p_limit INT DEFAULT 25)
RETURNS SETOF public.coaching_delivery_outbox
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$ BEGIN
 IF p_worker_id IS NULL OR length(btrim(p_worker_id))=0 THEN RAISE EXCEPTION 'worker_required'; END IF;
 WITH uncertain AS (UPDATE public.coaching_delivery_outbox SET state='uncertain',finished_at=clock_timestamp()
 WHERE state='dispatched' AND dispatched_at<=clock_timestamp()-interval '5 minutes'
 RETURNING user_id,delivery_key)
 UPDATE public.proactive_reservations r SET state='uncertain' FROM uncertain u
 WHERE r.user_id=u.user_id AND r.delivery_key=u.delivery_key;
 RETURN QUERY WITH candidates AS (
 SELECT user_id,delivery_key FROM public.coaching_delivery_outbox WHERE scheduled_at<=clock_timestamp()
 AND (state='pending' OR (state='claimed' AND claimed_at<=clock_timestamp()-interval '5 minutes'))
 ORDER BY scheduled_at LIMIT greatest(1,least(p_limit,100)) FOR UPDATE SKIP LOCKED)
 UPDATE public.coaching_delivery_outbox d SET state='claimed',claim_token=pg_catalog.gen_random_uuid(),
 claimed_at=clock_timestamp(),worker_id=p_worker_id FROM candidates c
 WHERE d.user_id=c.user_id AND d.delivery_key=c.delivery_key RETURNING d.*;
END $$;
CREATE FUNCTION public.mark_coaching_dispatch(p_user_id UUID,p_delivery_key TEXT,p_claim_token UUID)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE d public.coaching_delivery_outbox%ROWTYPE; p public.coaching_programs%ROWTYPE;
 u public.user_profiles%ROWTYPE; local_now TIMESTAMP; profile_now TIMESTAMP; wake TIME; sleep TIME; unanswered BIGINT;
 reply TIMESTAMPTZ; activation_allowed BOOLEAN:=FALSE; BEGIN
 SELECT * INTO d FROM public.coaching_delivery_outbox WHERE user_id=p_user_id AND delivery_key=p_delivery_key;
 IF NOT FOUND THEN RETURN FALSE; END IF;
 SELECT * INTO u FROM public.user_profiles WHERE user_id=p_user_id;
 IF u.supabase_auth_id IS NOT NULL THEN
   activation_allowed:=coalesce((public.get_activation_state(u.supabase_auth_id)->>'completed')::boolean,FALSE);
 END IF;
 SELECT * INTO p FROM public.coaching_programs WHERE program_id=d.program_id AND user_id=p_user_id FOR UPDATE;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-proactive:'||p_user_id,0));
 SELECT * INTO d FROM public.coaching_delivery_outbox WHERE user_id=p_user_id
   AND delivery_key=p_delivery_key FOR UPDATE;
 IF NOT FOUND OR d.state<>'claimed' OR d.claim_token IS DISTINCT FROM p_claim_token
    OR d.claimed_at<=clock_timestamp()-interval '5 minutes' THEN RETURN FALSE; END IF;
 SELECT * INTO u FROM public.user_profiles WHERE user_id=p_user_id;
 local_now:=clock_timestamp() AT TIME ZONE p.timezone;
 profile_now:=clock_timestamp() AT TIME ZONE coalesce(u.timezone,'UTC');
 wake:=coalesce(u.wake_time,'07:30')::time; sleep:=coalesce(u.sleep_time,'23:00')::time;
 SELECT last_reply_at INTO reply FROM public.coaching_delivery_replies
 WHERE user_id=p_user_id AND program_id=p.program_id;
 SELECT count(*) INTO unanswered FROM public.coaching_delivery_outbox
 WHERE program_id=p.program_id AND state IN ('accepted','uncertain','dispatched')
 AND (reply IS NULL OR coalesce(dispatched_at,scheduled_at)>reply);
 IF NOT activation_allowed OR p.state<>'active' OR p.version<>d.program_version OR clock_timestamp()<p.starts_at
    OR clock_timestamp()>=p.ends_at OR NOT public.has_coaching_consent(p_user_id)
    OR NOT EXISTS(SELECT 1 FROM public.mode_grants WHERE user_id=p_user_id AND mode_id='coach'
      AND revoked_at IS NULL AND expires_at>clock_timestamp())
    OR local_now::date<>d.local_day OR clock_timestamp()<d.scheduled_at
    OR clock_timestamp()>d.scheduled_at+interval '15 minutes'
    OR NOT (extract(isodow FROM local_now)::int=ANY(p.check_in_days))
    OR (CASE WHEN wake<sleep THEN NOT(profile_now::time>=wake AND profile_now::time<sleep)
             ELSE NOT(profile_now::time>=wake OR profile_now::time<sleep) END)
    OR EXISTS(SELECT 1 FROM public.proactive_reservations
      WHERE user_id=p_user_id AND delivery_key<>p_delivery_key AND kind='coaching'
      AND state<>'cancelled' AND (local_day=profile_now::date
        OR (scheduled_at AT TIME ZONE coalesce(u.timezone,'UTC'))::date=profile_now::date))
    OR (SELECT count(*) FROM public.proactive_reservations WHERE user_id=p_user_id
      AND state<>'cancelled' AND (local_day=profile_now::date
        OR (scheduled_at AT TIME ZONE coalesce(u.timezone,'UTC'))::date=profile_now::date))
      >greatest(0,coalesce(u.daily_message_budget,4))
    OR unanswered>=2 OR (unanswered=1 AND d.kind<>'follow_up')
    OR (unanswered=0 AND d.kind='follow_up') THEN
   UPDATE public.coaching_delivery_outbox SET state='cancelled',finished_at=clock_timestamp()
     WHERE user_id=p_user_id AND delivery_key=p_delivery_key;
   UPDATE public.proactive_reservations SET state='cancelled'
     WHERE user_id=p_user_id AND delivery_key=p_delivery_key AND state='reserved';
   RETURN FALSE;
 END IF;
 UPDATE public.coaching_delivery_outbox SET state='dispatched',dispatched_at=clock_timestamp()
 WHERE user_id=p_user_id AND delivery_key=p_delivery_key;
 UPDATE public.proactive_reservations SET state='dispatched'
 WHERE user_id=p_user_id AND delivery_key=p_delivery_key;
 RETURN TRUE;
END $$;
CREATE FUNCTION public.finish_coaching_delivery(p_user_id UUID,p_delivery_key TEXT,
 p_claim_token UUID,p_outcome TEXT) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE d public.coaching_delivery_outbox%ROWTYPE; outcome TEXT:=p_outcome; BEGIN
 IF outcome IS NULL OR outcome NOT IN ('accepted','rejected','uncertain','cancelled') THEN
   RAISE EXCEPTION 'invalid_coaching_outcome'; END IF;
 SELECT * INTO d FROM public.coaching_delivery_outbox WHERE user_id=p_user_id
 AND delivery_key=p_delivery_key FOR UPDATE;
 IF NOT FOUND OR d.claim_token IS DISTINCT FROM p_claim_token OR d.state NOT IN ('claimed','dispatched')
 THEN RETURN FALSE; END IF;
 IF d.state='dispatched' AND outcome='cancelled' THEN outcome:='uncertain'; END IF;
 UPDATE public.coaching_delivery_outbox SET state=outcome,finished_at=clock_timestamp()
 WHERE user_id=p_user_id AND delivery_key=p_delivery_key;
 UPDATE public.proactive_reservations SET state=outcome WHERE user_id=p_user_id AND delivery_key=p_delivery_key;
 RETURN TRUE;
END $$;
CREATE FUNCTION public.cancel_inactive_coaching_deliveries() RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE owner_id UUID; affected_program UUID; BEGIN
 owner_id:=CASE WHEN TG_OP='DELETE' THEN OLD.user_id ELSE NEW.user_id END;
 affected_program:=CASE WHEN TG_OP='DELETE' THEN OLD.program_id ELSE NEW.program_id END;
 IF TG_OP='DELETE' OR NEW.state<>'active' THEN
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('amigo-proactive:'||owner_id,0));
  UPDATE public.coaching_delivery_outbox SET state='cancelled',finished_at=clock_timestamp()
  WHERE program_id=affected_program AND state IN ('pending','claimed');
  UPDATE public.proactive_reservations SET state='cancelled'
  WHERE program_id=affected_program AND state='reserved';
 END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER coaching_inactive_cancels_delivery AFTER UPDATE OF state ON public.coaching_programs
 FOR EACH ROW EXECUTE FUNCTION public.cancel_inactive_coaching_deliveries();
CREATE TRIGGER coaching_deleted_cancels_delivery BEFORE DELETE ON public.coaching_programs
 FOR EACH ROW EXECUTE FUNCTION public.cancel_inactive_coaching_deliveries();

DO $$ DECLARE fn RECORD; BEGIN
 FOR fn IN SELECT p.oid::regprocedure signature FROM pg_catalog.pg_proc p
 JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname IN (
 'reserve_proactive_delivery','release_proactive_delivery','set_proactive_consent','get_proactive_consent',
 'set_coaching_consent','has_coaching_consent',
 'note_coaching_reply','get_coaching_delivery_history','enqueue_coaching_delivery',
 'claim_coaching_deliveries','mark_coaching_dispatch','finish_coaching_delivery',
 'cancel_inactive_coaching_deliveries') LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated',fn.signature);
   IF fn.signature::text NOT LIKE 'cancel_inactive_coaching_deliveries%%' THEN
     EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',fn.signature);
   END IF;
 END LOOP;
END $$;
DO $$ BEGIN
 IF to_regclass('public.proactive_reservations') IS NULL
 OR to_regclass('public.coaching_delivery_outbox') IS NULL
 OR to_regprocedure('public.mark_coaching_dispatch(uuid,text,uuid)') IS NULL
 OR to_regprocedure('public.enqueue_coaching_delivery(uuid,uuid,bigint,text,date,text,timestamptz)') IS NULL
 OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger WHERE tgname='coaching_inactive_cancels_delivery')
 OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger WHERE tgname='reminder_budget_admission')
 OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger WHERE tgname='reminder_budget_status')
 THEN RAISE EXCEPTION '019 objects were not created'; END IF;
 INSERT INTO public.schema_migrations(version) VALUES(19);
END $$;
COMMIT;
