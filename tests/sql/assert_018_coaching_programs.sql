\set ON_ERROR_STOP on
BEGIN;
DO $$
DECLARE u UUID; other_u UUID; p UUID; token TEXT; r JSONB; original_end TIMESTAMPTZ; cfg JSONB;
BEGIN
 IF public.get_app_schema_version()<>18 THEN RAISE EXCEPTION '018 not reported'; END IF;
 INSERT INTO public.user_profiles(telegram_chat_id,supabase_auth_id)
  VALUES(91018001,'00000000-0000-0000-0000-000000018001') RETURNING user_id INTO u;
 INSERT INTO public.user_profiles(telegram_chat_id,supabase_auth_id)
  VALUES(91018002,'00000000-0000-0000-0000-000000018002') RETURNING user_id INTO other_u;
 cfg:='{"goal":"Walk outside","success_measure":"I choose three walks","check_in_days":[1,5],"check_in_time":"18:00","timezone":"Asia/Kathmandu"}';
 r:=public.coaching_program_command(u,NULL,NULL,'draft','draft','draft',cfg);
 p:=(r->'program'->>'program_id')::UUID;
 IF r->'program'->>'state'<>'draft' OR (r->'program'->>'starts_at') IS NOT NULL
  THEN RAISE EXCEPTION 'draft started automatically'; END IF;
 IF public.coaching_program_command(u,NULL,NULL,'draft','draft','draft',cfg)<>r
  THEN RAISE EXCEPTION 'draft replay changed result'; END IF;
 BEGIN
  PERFORM public.coaching_program_command(u,NULL,NULL,'draft','second','second',cfg);
  RAISE EXCEPTION 'second nonterminal program accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_invalid_transition' THEN RAISE; END IF; END;
 BEGIN
  PERFORM public.coaching_program_command(u,p,1,'activate','no-consent','no-consent');
  RAISE EXCEPTION 'activation without participant token accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_approval_required' THEN RAISE; END IF; END;
 token:=public.issue_coaching_approval(u,p,1);
 BEGIN
  PERFORM public.confirm_coaching_approval(other_u,token,'wrong-owner','wrong-owner');
  RAISE EXCEPTION 'other owner consumed approval';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_approval_required' THEN RAISE; END IF; END;
 r:=public.confirm_coaching_approval(u,token,'approve','approve');
 IF r->'program'->>'state'<>'active' OR (r->'program'->>'version')::INT<>2
    OR (r->'program'->>'ends_at')::TIMESTAMPTZ-(r->'program'->>'starts_at')::TIMESTAMPTZ<>interval '336 hours'
  THEN RAISE EXCEPTION 'approved activation term/version incorrect'; END IF;
 original_end:=(r->'program'->>'ends_at')::TIMESTAMPTZ;
 IF public.confirm_coaching_approval(u,token,'approve','approve')<>r THEN RAISE EXCEPTION 'approval replay changed'; END IF;
 BEGIN
  PERFORM public.confirm_coaching_approval(u,token,'approve','different');
  RAISE EXCEPTION 'idempotency hash conflict accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'idempotency_key_conflict' THEN RAISE; END IF; END;
 BEGIN
  PERFORM public.coaching_program_command(other_u,p,2,'stop','cross','cross');
  RAISE EXCEPTION 'cross-owner mutation accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_program_unavailable' THEN RAISE; END IF; END;
 r:=public.coaching_program_command(u,p,2,'record_progress','progress','progress','{"progress_text":"I took one walk."}');
 IF r->'entry'->>'kind'<>'progress' OR r->'entry'->>'participant_text'<>'I took one walk.' THEN
  RAISE EXCEPTION 'participant progress changed'; END IF;
 r:=public.coaching_program_command(u,p,3,'record_weekly_choice','weekly','weekly','{"weekly_choice":"continue"}');
 IF (r->'program'->>'ends_at')::TIMESTAMPTZ<>original_end THEN RAISE EXCEPTION 'continue silently extended'; END IF;
 r:=public.coaching_program_command(u,p,4,'pause','pause','pause');
 r:=public.coaching_program_command(u,p,5,'revise','revise','revise',cfg);
 token:=public.issue_coaching_approval(u,p,6);
 r:=public.confirm_coaching_approval(u,token,'approve-revision','approve-revision');
 IF (r->'program'->>'ends_at')::TIMESTAMPTZ<>original_end THEN RAISE EXCEPTION 'revision reset term'; END IF;
 r:=public.coaching_program_command(u,p,7,'extend','extend','extend','{"extension_days":2}');
 IF (r->'program'->>'ends_at')::TIMESTAMPTZ<>original_end+interval '48 hours' THEN RAISE EXCEPTION 'explicit extension wrong'; END IF;
 r:=public.coaching_program_command(u,p,8,'stop','stop','stop');
 IF r->'program'->>'state'<>'stopped' THEN RAISE EXCEPTION 'stop failed'; END IF;
 BEGIN
  PERFORM public.coaching_program_command(u,p,9,'resume','terminal','terminal');
  RAISE EXCEPTION 'terminal program resumed';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_invalid_transition' THEN RAISE; END IF; END;
 r:=public.coaching_program_command(other_u,NULL,NULL,'draft','other','other',cfg);
 PERFORM set_config('amigo.coach_user',u::TEXT,TRUE);
 PERFORM set_config('amigo.coach_program',p::TEXT,TRUE);
 IF jsonb_array_length(public.export_coaching_data(u)->'programs')<>1
    OR jsonb_array_length(public.export_coaching_data(u)->'entries')<>9
  THEN RAISE EXCEPTION 'owned export incomplete'; END IF;
 -- Exercise expiry and version invalidation on a fresh draft; no sleeps or provider calls.
 r:=public.coaching_program_command(u,NULL,NULL,'draft','draft-two','draft-two',cfg);
 p:=(r->'program'->>'program_id')::UUID;
 token:=public.issue_coaching_approval(u,p,1);
 UPDATE public.coaching_approvals SET expires_at=clock_timestamp()-interval '1 second' WHERE program_id=p;
 BEGIN
  PERFORM public.confirm_coaching_approval(u,token,'expired','expired');
  RAISE EXCEPTION 'expired approval accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_approval_required' THEN RAISE; END IF; END;
 r:=public.coaching_program_command(u,p,1,'revise','revise-two','revise-two',cfg);
 token:=public.issue_coaching_approval(u,p,2);
 r:=public.coaching_program_command(u,p,2,'revise','revise-three','revise-three',cfg);
 BEGIN
  PERFORM public.confirm_coaching_approval(u,token,'stale-approval','stale-approval');
  RAISE EXCEPTION 'old summary approval survived revision';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_stale_version' THEN RAISE; END IF; END;
 token:=public.issue_coaching_approval(u,p,3);
 r:=public.confirm_coaching_approval(u,token,'approve-two','approve-two');
 BEGIN
  PERFORM public.coaching_program_command(u,p,3,'stop','stale-stop','stale-stop');
  RAISE EXCEPTION 'stale optimistic mutation accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_stale_version' THEN RAISE; END IF; END;
 r:=public.coaching_program_command(u,p,4,'pause','pause-two','pause-two');
 UPDATE public.coaching_programs SET starts_at=clock_timestamp()-interval '15 days',
  ends_at=clock_timestamp()-interval '1 day' WHERE program_id=p;
 r:=public.complete_due_coaching_programs();
 IF jsonb_array_length(r)<>1 OR (SELECT state FROM public.coaching_programs WHERE program_id=p)<>'completed'
    OR public.complete_due_coaching_programs()<>'[]'::jsonb THEN
  RAISE EXCEPTION 'paused program did not complete once at term end'; END IF;
END $$;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000018001',TRUE);
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.coaching_programs) OR EXISTS(
  SELECT 1 FROM public.coaching_programs WHERE user_id<>current_setting('amigo.coach_user')::UUID)
  OR EXISTS(SELECT 1 FROM public.coaching_entries WHERE user_id<>current_setting('amigo.coach_user')::UUID)
 THEN RAISE EXCEPTION 'coaching RLS owner isolation failed'; END IF;
END $$;
RESET ROLE;
DO $$ DECLARE t TEXT; f TEXT; BEGIN
 FOREACH t IN ARRAY ARRAY['coaching_programs','coaching_entries','coaching_approvals','coaching_command_receipts'] LOOP
  IF has_table_privilege('anon','public.'||t,'SELECT,INSERT,UPDATE,DELETE')
     OR has_table_privilege('service_role','public.'||t,'INSERT,UPDATE,DELETE')
     OR has_table_privilege('authenticated','public.'||t,'INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION 'coaching direct data mutation privilege retained'; END IF;
 END LOOP;
 FOREACH f IN ARRAY ARRAY['coaching_program_command(uuid,uuid,integer,text,text,text,jsonb)',
 'issue_coaching_approval(uuid,uuid,integer)','confirm_coaching_approval(uuid,text,text,text)',
 'complete_due_coaching_programs()','export_coaching_data(uuid)','delete_coaching_data(uuid,text)'] LOOP
  IF has_function_privilege('anon','public.'||f,'EXECUTE')
     OR has_function_privilege('authenticated','public.'||f,'EXECUTE')
     OR NOT has_function_privilege('service_role','public.'||f,'EXECUTE') THEN
   RAISE EXCEPTION 'coaching RPC privilege incorrect'; END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_proc WHERE oid=('public.'||f)::regprocedure
                AND prosecdef AND proconfig @> ARRAY['search_path=""']) THEN
   RAISE EXCEPTION 'coaching RPC search_path/definer incorrect'; END IF;
 END LOOP;
 PERFORM public.delete_coaching_data(current_setting('amigo.coach_user')::UUID,'verified-local-fixture');
 IF public.export_coaching_data(current_setting('amigo.coach_user')::UUID)<>'{"programs":[],"entries":[]}'::jsonb
    OR EXISTS(SELECT 1 FROM public.coaching_approvals WHERE user_id=current_setting('amigo.coach_user')::UUID)
    OR EXISTS(SELECT 1 FROM public.coaching_command_receipts WHERE user_id=current_setting('amigo.coach_user')::UUID)
 THEN RAISE EXCEPTION 'coaching deletion retained content or approval/receipt artifacts'; END IF;
 IF (SELECT count(*) FROM public.coaching_programs)<>1 THEN RAISE EXCEPTION 'deletion crossed owner'; END IF;
END $$;
ROLLBACK;
