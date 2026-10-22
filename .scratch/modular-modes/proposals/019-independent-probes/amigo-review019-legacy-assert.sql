DO $$ DECLARE u UUID:='01901901-0000-4000-8000-000000000001'; label TEXT; expected TEXT; actual TEXT; BEGIN
 IF (SELECT count(*) FROM public.proactive_reservations WHERE user_id=u)<>6 OR (SELECT count(*) FROM public.proactive_reservations WHERE user_id=u AND legacy_debt)<>4 THEN RAISE EXCEPTION 'legacy debt backfill count wrong'; END IF;
 FOREACH label IN ARRAY ARRAY['pending','pending_attempted','pending_accepted','sending','sent','cancelled_attempted'] LOOP
  expected:=CASE WHEN label='pending' THEN 'reserved' WHEN label IN ('pending_accepted','sent') THEN 'accepted' ELSE 'uncertain' END;
  SELECT p.state INTO actual FROM public.proactive_reservations p JOIN public.reminders r ON p.delivery_key='reminder:'||r.reminder_id JOIN public.tasks t ON t.task_id=r.task_id WHERE p.user_id=u AND t.title=label;
  IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'legacy label % expected % actual %',label,expected,actual; END IF;
 END LOOP;
END $$;
