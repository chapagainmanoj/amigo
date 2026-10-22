DO $$ DECLARE u UUID; auth UUID:=gen_random_uuid(); t UUID; rem UUID; p UUID; BEGIN
 INSERT INTO public.user_profiles(telegram_chat_id,timezone,daily_message_budget,wake_time,sleep_time,supabase_auth_id) VALUES(910199995,'UTC',4,'00:00','00:00',auth) RETURNING user_id INTO u;
 INSERT INTO public.tasks(user_id,title,status) VALUES(u,'Mixed fixture Activation','completed') RETURNING task_id INTO t;
 INSERT INTO public.reminders(user_id,task_id,scheduled_time,status,telegram_message_id,intended_local_date,intended_local_time,intended_timezone) VALUES(u,t,clock_timestamp()-interval '1 day','acknowledged',1,(clock_timestamp() AT TIME ZONE 'UTC')::date-1,'12:00','UTC') RETURNING reminder_id INTO rem;
 INSERT INTO public.activation_journeys(auth_id,policy_version,acknowledged_at,profile_completed_at,test_task_id,test_reminder_id,test_confirmed_at) VALUES(auth,'fictional-test-policy',clock_timestamp(),clock_timestamp(),t,rem,clock_timestamp());
 IF (public.get_activation_state(auth)->>'completed')::boolean IS NOT TRUE THEN RAISE EXCEPTION 'mixed fixture Activation failed'; END IF;
 INSERT INTO public.coaching_programs(user_id,goal,success_measure,check_in_days,check_in_time,timezone,state,starts_at,ends_at) VALUES(u,'Mixed fictional goal','Chosen measure',ARRAY[1,2,3,4,5,6,7],'12:00','UTC','active',clock_timestamp()-interval '1 day',clock_timestamp()+interval '13 days') RETURNING program_id INTO p;
 PERFORM public.grant_mode(u,'coach','independent-review','fictional mixed concurrency'); PERFORM public.set_coaching_consent(u,'coaching-v1');
END $$;
