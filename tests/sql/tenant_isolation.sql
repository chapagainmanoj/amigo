\set ON_ERROR_STOP on

INSERT INTO public.user_profiles(user_id, telegram_chat_id, supabase_auth_id, name)
VALUES
  (
    'aaaaaaaa-0000-0000-0000-000000000001',
    1001,
    'aaaaaaaa-1111-1111-1111-111111111111',
    'Participant A'
  ),
  (
    'bbbbbbbb-0000-0000-0000-000000000002',
    2002,
    'bbbbbbbb-2222-2222-2222-222222222222',
    'Participant B'
  );

INSERT INTO public.sessions(session_id, user_id, session_type)
VALUES
  (
    'aaaaaaaa-3000-0000-0000-000000000001',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'casual'
  ),
  (
    'bbbbbbbb-3000-0000-0000-000000000002',
    'bbbbbbbb-0000-0000-0000-000000000002',
    'casual'
  );

INSERT INTO public.tasks(task_id, user_id, title, source_session_id)
VALUES
  (
    'aaaaaaaa-4000-0000-0000-000000000001',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'Participant A task',
    'aaaaaaaa-3000-0000-0000-000000000001'
  ),
  (
    'bbbbbbbb-4000-0000-0000-000000000002',
    'bbbbbbbb-0000-0000-0000-000000000002',
    'Participant B task',
    'bbbbbbbb-3000-0000-0000-000000000002'
  );

INSERT INTO public.reminders(
  reminder_id,
  task_id,
  user_id,
  scheduled_time,
  intended_local_date,
  intended_local_time,
  intended_timezone
)
VALUES
  (
    'aaaaaaaa-5000-0000-0000-000000000001',
    'aaaaaaaa-4000-0000-0000-000000000001',
    'aaaaaaaa-0000-0000-0000-000000000001',
    now() + INTERVAL '1 hour',
    current_date,
    TIME '12:00:00',
    'UTC'
  ),
  (
    'bbbbbbbb-5000-0000-0000-000000000002',
    'bbbbbbbb-4000-0000-0000-000000000002',
    'bbbbbbbb-0000-0000-0000-000000000002',
    now() + INTERVAL '1 hour',
    current_date,
    TIME '12:00:00',
    'UTC'
  );

INSERT INTO public.messages(message_id, session_id, user_id, role, content)
VALUES
  (
    'aaaaaaaa-6000-0000-0000-000000000001',
    'aaaaaaaa-3000-0000-0000-000000000001',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'user',
    'Participant A message'
  ),
  (
    'bbbbbbbb-6000-0000-0000-000000000002',
    'bbbbbbbb-3000-0000-0000-000000000002',
    'bbbbbbbb-0000-0000-0000-000000000002',
    'user',
    'Participant B message'
  );

INSERT INTO public.feedback(feedback_id, user_id, session_id, content)
VALUES
  (
    'aaaaaaaa-7000-0000-0000-000000000001',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'aaaaaaaa-3000-0000-0000-000000000001',
    'Participant A feedback'
  ),
  (
    'bbbbbbbb-7000-0000-0000-000000000002',
    'bbbbbbbb-0000-0000-0000-000000000002',
    'bbbbbbbb-3000-0000-0000-000000000002',
    'Participant B feedback'
  );

INSERT INTO public.usage_events(id, user_id, model, session_id)
VALUES
  (
    'aaaaaaaa-8000-0000-0000-000000000001',
    'aaaaaaaa-0000-0000-0000-000000000001',
    'test-model',
    'aaaaaaaa-3000-0000-0000-000000000001'
  ),
  (
    'bbbbbbbb-8000-0000-0000-000000000002',
    'bbbbbbbb-0000-0000-0000-000000000002',
    'test-model',
    'bbbbbbbb-3000-0000-0000-000000000002'
  );

DO $$
DECLARE
  table_name TEXT;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'user_profiles',
    'tasks',
    'reminders',
    'sessions',
    'messages',
    'feedback',
    'usage_events',
    'pairing_tokens',
    'command_receipts',
    'scheduler_outbox'
  ]
  LOOP
    IF NOT (
      SELECT relrowsecurity
      FROM pg_class
      WHERE oid = format('public.%I', table_name)::regclass
    ) THEN
      RAISE EXCEPTION 'RLS is disabled for %', table_name;
    END IF;
  END LOOP;
END;
$$;

SET ROLE authenticated;
SET request.jwt.claim.sub = 'aaaaaaaa-1111-1111-1111-111111111111';

DO $$
BEGIN
  IF (SELECT count(*) FROM public.user_profiles) <> 1 THEN
    RAISE EXCEPTION 'Profile isolation failed';
  END IF;
  IF (SELECT count(*) FROM public.tasks) <> 1 THEN
    RAISE EXCEPTION 'Task isolation failed';
  END IF;
  IF (SELECT count(*) FROM public.reminders) <> 1 THEN
    RAISE EXCEPTION 'Reminder isolation failed';
  END IF;
  IF (SELECT count(*) FROM public.sessions) <> 1 THEN
    RAISE EXCEPTION 'Session isolation failed';
  END IF;
  IF (SELECT count(*) FROM public.messages) <> 1 THEN
    RAISE EXCEPTION 'Message isolation failed';
  END IF;

  IF has_table_privilege(current_user, 'public.feedback', 'SELECT')
    OR has_table_privilege(current_user, 'public.usage_events', 'SELECT')
    OR has_table_privilege(current_user, 'public.pairing_tokens', 'SELECT')
    OR has_table_privilege(current_user, 'public.command_receipts', 'SELECT')
    OR has_table_privilege(current_user, 'public.scheduler_outbox', 'SELECT')
  THEN
    RAISE EXCEPTION 'Authenticated role retained backend-only read access';
  END IF;

  IF has_table_privilege(current_user, 'public.user_profiles', 'UPDATE')
    OR has_table_privilege(current_user, 'public.tasks', 'UPDATE')
    OR has_table_privilege(current_user, 'public.tasks', 'DELETE')
    OR has_table_privilege(current_user, 'public.reminders', 'INSERT')
    OR has_table_privilege(current_user, 'public.reminders', 'UPDATE')
    OR has_table_privilege(current_user, 'public.reminders', 'DELETE')
  THEN
    RAISE EXCEPTION 'Authenticated role retained a forbidden mutation privilege';
  END IF;

  IF has_function_privilege(
      current_user,
      'public.issue_pairing_token(text,uuid,timestamptz)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.complete_pairing(text,bigint)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.schedule_reminder_command(uuid,text,text,uuid,uuid,timestamptz,date,time,text)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.cancel_reminder_command(uuid,text,text,uuid)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.claim_scheduler_outbox(integer,text)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.complete_scheduler_outbox(uuid,uuid,boolean,text)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.resolve_task_command(uuid,text,text,uuid,task_status,bigint,uuid)',
      'EXECUTE'
    )
    OR has_function_privilege(
      current_user,
      'public.apply_later_command(uuid,text,text,uuid,bigint,integer,timestamptz,date,time,text,boolean,date)',
      'EXECUTE'
    )
  THEN
    RAISE EXCEPTION 'Authenticated role retained a service-role RPC';
  END IF;

  BEGIN
    UPDATE public.tasks
    SET title = 'Direct browser update'
    WHERE task_id = 'aaaaaaaa-4000-0000-0000-000000000001';
    RAISE EXCEPTION 'Authenticated direct Task update unexpectedly succeeded';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;

  BEGIN
    DELETE FROM public.tasks
    WHERE task_id = 'aaaaaaaa-4000-0000-0000-000000000001';
    RAISE EXCEPTION 'Authenticated direct Task delete unexpectedly succeeded';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;

  BEGIN
    UPDATE public.reminders
    SET scheduled_time = now() + INTERVAL '2 hours'
    WHERE reminder_id = 'aaaaaaaa-5000-0000-0000-000000000001';
    RAISE EXCEPTION 'Authenticated direct Reminder update unexpectedly succeeded';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;

  BEGIN
    INSERT INTO public.tasks(user_id, title, status)
    VALUES (
      'bbbbbbbb-0000-0000-0000-000000000002',
      'Cross-tenant task',
      'pending'
    );
    RAISE EXCEPTION 'Cross-tenant Task insert unexpectedly succeeded';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;

  BEGIN
    INSERT INTO public.tasks(user_id, title, status, source_session_id)
    VALUES (
      'aaaaaaaa-0000-0000-0000-000000000001',
      'Cross-linked Task',
      'pending',
      'bbbbbbbb-3000-0000-0000-000000000002'
    );
    RAISE EXCEPTION 'Cross-tenant Task-to-Session link unexpectedly succeeded';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;

END;
$$;

RESET ROLE;
RESET request.jwt.claim.sub;

SET ROLE anon;

DO $$
BEGIN
  IF has_table_privilege(current_user, 'public.user_profiles', 'SELECT')
    OR has_table_privilege(current_user, 'public.tasks', 'SELECT')
    OR has_table_privilege(current_user, 'public.reminders', 'SELECT')
    OR has_table_privilege(current_user, 'public.sessions', 'SELECT')
    OR has_table_privilege(current_user, 'public.messages', 'SELECT')
    OR has_table_privilege(current_user, 'public.feedback', 'SELECT')
    OR has_table_privilege(current_user, 'public.usage_events', 'SELECT')
    OR has_table_privilege(current_user, 'public.pairing_tokens', 'SELECT')
    OR has_table_privilege(current_user, 'public.command_receipts', 'SELECT')
    OR has_table_privilege(current_user, 'public.scheduler_outbox', 'SELECT')
  THEN
    RAISE EXCEPTION 'Anonymous role retained product-table access';
  END IF;
END;
$$;

RESET ROLE;

SET ROLE service_role;

DO $$
BEGIN
  IF (SELECT count(*) FROM public.user_profiles) <> 2
    OR (SELECT count(*) FROM public.tasks) <> 2
    OR (SELECT count(*) FROM public.reminders) <> 2
    OR (SELECT count(*) FROM public.sessions) <> 2
    OR (SELECT count(*) FROM public.messages) <> 2
    OR (SELECT count(*) FROM public.feedback) <> 2
    OR (SELECT count(*) FROM public.usage_events) <> 2
  THEN
    RAISE EXCEPTION 'Service role cannot inspect all tenant rows';
  END IF;

  IF NOT has_function_privilege(
      current_user,
      'public.issue_pairing_token(text,uuid,timestamptz)',
      'EXECUTE'
    )
    OR NOT has_function_privilege(
      current_user,
      'public.complete_pairing(text,bigint)',
      'EXECUTE'
    )
    OR NOT has_function_privilege(
      current_user,
      'public.schedule_reminder_command(uuid,text,text,uuid,uuid,timestamptz,date,time,text)',
      'EXECUTE'
    )
    OR NOT has_function_privilege(
      current_user,
      'public.cancel_reminder_command(uuid,text,text,uuid)',
      'EXECUTE'
    )
    OR NOT has_function_privilege(
      current_user,
      'public.claim_scheduler_outbox(integer,text)',
      'EXECUTE'
    )
    OR NOT has_function_privilege(
      current_user,
      'public.complete_scheduler_outbox(uuid,uuid,boolean,text)',
      'EXECUTE'
    )
    OR NOT has_function_privilege(
      current_user,
      'public.resolve_task_command(uuid,text,text,uuid,task_status,bigint,uuid)',
      'EXECUTE'
    )
    OR NOT has_function_privilege(
      current_user,
      'public.apply_later_command(uuid,text,text,uuid,bigint,integer,timestamptz,date,time,text,boolean,date)',
      'EXECUTE'
    )
  THEN
    RAISE EXCEPTION 'Service role cannot execute backend RPCs';
  END IF;
END;
$$;

RESET ROLE;
