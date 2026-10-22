BEGIN;
DO $$ DECLARE u UUID; p UUID; t TEXT; r JSONB; cfg JSONB; BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id) VALUES(910189991) RETURNING user_id INTO u;
 cfg:='{"goal":"Synthetic","success_measure":"Chosen","check_in_days":[1],"check_in_time":"18:00","timezone":"UTC"}';
 r:=public.coaching_program_command(u,NULL,NULL,'draft','draft','draft',cfg); p:=(r->'program'->>'program_id')::UUID;
 t:=public.issue_coaching_approval(u,p,1);
 UPDATE public.coaching_approvals SET expires_at=clock_timestamp()-interval '1 second' WHERE user_id=u;
 BEGIN
  PERFORM public.confirm_coaching_approval(u,t,'expired','expired');
  RAISE EXCEPTION 'expired approval accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_approval_required' THEN RAISE; END IF; END;
 t:=public.issue_coaching_approval(u,p,1);
 PERFORM public.coaching_program_command(u,p,1,'revise','revise','revise',cfg||'{"goal":"Changed"}'::jsonb);
 BEGIN
  PERFORM public.confirm_coaching_approval(u,t,'stale','stale');
  RAISE EXCEPTION 'stale summary token accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_stale_version' THEN RAISE; END IF; END;
 t:=public.issue_coaching_approval(u,p,2);
 PERFORM public.confirm_coaching_approval(u,t,'approve','approve');
 BEGIN
  PERFORM public.coaching_program_command(u,p,2,'stop','stale-stop','stale-stop');
  RAISE EXCEPTION 'stale optimistic version accepted';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'coaching_stale_version' THEN RAISE; END IF; END;
 UPDATE public.coaching_programs SET starts_at=clock_timestamp()-interval '15 days',ends_at=clock_timestamp()-interval '1 day' WHERE program_id=p;
 PERFORM public.complete_due_coaching_programs(); PERFORM public.complete_due_coaching_programs();
 IF (SELECT state FROM public.coaching_programs WHERE program_id=p)<>'completed' OR
    (SELECT count(*) FROM public.coaching_entries WHERE program_id=p AND action='complete')<>1 THEN
  RAISE EXCEPTION 'completion not exactly once'; END IF;
 IF has_table_privilege('service_role','public.coaching_approvals','SELECT') OR
    has_table_privilege('service_role','public.coaching_command_receipts','SELECT') THEN
  RAISE EXCEPTION 'raw approval/receipt service read allowed'; END IF;
END $$;
ROLLBACK;
