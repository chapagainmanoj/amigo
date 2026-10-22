BEGIN;
DO $$ DECLARE u UUID; task UUID; r JSONB; old UUID; old_row JSONB; task_row JSONB; outbox_count INT; receipt_count INT; later_at TIMESTAMPTZ:=date_trunc('minute',clock_timestamp())+interval '1 day'; first_at TIMESTAMPTZ:=date_trunc('minute',clock_timestamp())+interval '1 minute'; BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id,timezone,daily_message_budget) VALUES(910199993,'UTC',1) RETURNING user_id INTO u;
 INSERT INTO public.tasks(user_id,title,status) VALUES(u,'Fictional atomic budget test','pending') RETURNING task_id INTO task;
 r:=public.schedule_reminder_command(u,'first',repeat('a',64),task,NULL,first_at,(first_at AT TIME ZONE 'UTC')::date,(first_at AT TIME ZONE 'UTC')::time,'UTC');
 old:=(r->'reminder'->>'reminder_id')::UUID;
 PERFORM public.reserve_proactive_delivery(u,'tomorrow:full','recovery',later_at);
 SELECT to_jsonb(x) INTO old_row FROM public.reminders x WHERE reminder_id=old;
 SELECT to_jsonb(x) INTO task_row FROM public.tasks x WHERE task_id=task;
 SELECT count(*) INTO outbox_count FROM public.scheduler_outbox WHERE user_id=u;
 SELECT count(*) INTO receipt_count FROM public.command_receipts WHERE user_id=u;
 BEGIN
  PERFORM public.schedule_reminder_command(u,'refused-replace',repeat('b',64),NULL,old,later_at,(later_at AT TIME ZONE 'UTC')::date,(later_at AT TIME ZONE 'UTC')::time,'UTC');
  RAISE EXCEPTION 'full budget accepted replacement';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'proactive_budget_exhausted' THEN RAISE; END IF; END;
 BEGIN
  PERFORM public.apply_later_command(u,'refused-later',repeat('c',64),old,(task_row->>'version')::bigint,1,later_at,(later_at AT TIME ZONE 'UTC')::date,(later_at AT TIME ZONE 'UTC')::time,'UTC',false,NULL);
  RAISE EXCEPTION 'full budget accepted Later';
 EXCEPTION WHEN raise_exception THEN IF SQLERRM<>'proactive_budget_exhausted' THEN RAISE; END IF; END;
 IF old_row<>(SELECT to_jsonb(x) FROM public.reminders x WHERE reminder_id=old) OR task_row<>(SELECT to_jsonb(x) FROM public.tasks x WHERE task_id=task) OR
    outbox_count<>(SELECT count(*) FROM public.scheduler_outbox WHERE user_id=u) OR receipt_count<>(SELECT count(*) FROM public.command_receipts WHERE user_id=u) OR
    (SELECT count(*) FROM public.reminders WHERE user_id=u)<>1 THEN RAISE EXCEPTION 'refused command leaked cancellation/version/outbox/receipt'; END IF;
 IF (SELECT state FROM public.proactive_reservations WHERE user_id=u AND delivery_key='reminder:'||old)<>'reserved' THEN RAISE EXCEPTION 'rollback released original budget'; END IF;
 UPDATE public.reminders SET status='cancelled' WHERE reminder_id=old;
 IF public.reserve_proactive_delivery(u,'new:after-unsent-cancel','reminder',first_at)->>'status'<>'reserved' THEN RAISE EXCEPTION 'unsent cancellation failed to free slot'; END IF;
 PERFORM public.release_proactive_delivery(u,'new:after-unsent-cancel');
 INSERT INTO public.reminders(user_id,task_id,scheduled_time,status,intended_local_date,intended_local_time,intended_timezone)
 VALUES(u,task,first_at,'pending',(first_at AT TIME ZONE 'UTC')::date,(first_at AT TIME ZONE 'UTC')::time,'UTC') RETURNING reminder_id INTO old;
 UPDATE public.reminders SET status='sending' WHERE reminder_id=old;
 UPDATE public.reminders SET status='cancelled' WHERE reminder_id=old;
 IF public.reserve_proactive_delivery(u,'new:after-attempt','reminder',first_at)->>'status'<>'budget_exhausted' THEN RAISE EXCEPTION 'attempted cancellation reopened capacity'; END IF;
 IF (SELECT state FROM public.proactive_reservations WHERE user_id=u AND delivery_key='reminder:'||old)<>'dispatched' THEN RAISE EXCEPTION 'attempted debt state lost'; END IF;
END $$;
ROLLBACK;
