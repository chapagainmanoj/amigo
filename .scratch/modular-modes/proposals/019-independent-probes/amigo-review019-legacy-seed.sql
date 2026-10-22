DO $$ DECLARE u UUID:='01901901-0000-4000-8000-000000000001'; t UUID; r UUID; label TEXT; state TEXT; BEGIN
 INSERT INTO public.user_profiles(user_id,telegram_chat_id,timezone,daily_message_budget) VALUES(u,910199994,'UTC',2);
 FOREACH label IN ARRAY ARRAY['pending','pending_attempted','pending_accepted','sending','sent','cancelled_attempted','cancelled_pristine'] LOOP
  state:=CASE WHEN label LIKE 'pending%' THEN 'pending' WHEN label LIKE 'cancelled%' THEN 'cancelled' ELSE label END;
  INSERT INTO public.tasks(user_id,title,status) VALUES(u,label,'pending') RETURNING task_id INTO t;
  INSERT INTO public.reminders(user_id,task_id,scheduled_time,status,telegram_message_id,intended_local_date,intended_local_time,intended_timezone)
  VALUES(u,t,clock_timestamp(),state::public.reminder_status,CASE WHEN label='pending_accepted' THEN 7 END,(clock_timestamp() AT TIME ZONE 'UTC')::date,(clock_timestamp() AT TIME ZONE 'UTC')::time,'UTC') RETURNING reminder_id INTO r;
  IF label IN ('pending_attempted','cancelled_attempted') THEN
   UPDATE public.reminder_occurrences SET first_claimed_at=clock_timestamp() WHERE reminder_id=r;
  END IF;
 END LOOP;
END $$;
