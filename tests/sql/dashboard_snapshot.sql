INSERT INTO public.user_profiles (user_id, telegram_chat_id, timezone, session_timeout_minutes)
VALUES
  ('10000000-0000-0000-0000-000000000001', 91001, 'Pacific/Kiritimati', 120),
  ('20000000-0000-0000-0000-000000000002', 92002, 'UTC', 120);

INSERT INTO public.tasks (task_id, user_id, title, status, due_date, version)
VALUES
  ('11000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'Today pending', 'pending', (statement_timestamp() AT TIME ZONE 'Pacific/Kiritimati')::date, 1),
  ('11000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', 'Today done', 'completed', (statement_timestamp() AT TIME ZONE 'Pacific/Kiritimati')::date, 2),
  ('11000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000001', 'Inbox', 'pending', NULL, 1),
  ('11000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000001', 'Carried', 'pending', (statement_timestamp() AT TIME ZONE 'Pacific/Kiritimati')::date - 1, 1),
  ('22000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000002', 'Other tenant', 'pending', NULL, 1);

INSERT INTO public.reminders (
  reminder_id, task_id, user_id, scheduled_time, status,
  intended_local_date, intended_local_time, intended_timezone
)
VALUES (
  '12000000-0000-0000-0000-000000000001',
  '11000000-0000-0000-0000-000000000004',
  '10000000-0000-0000-0000-000000000001',
  statement_timestamp() - interval '1 minute',
  'pending',
  (statement_timestamp() AT TIME ZONE 'Pacific/Kiritimati')::date - 1,
  '09:00',
  'Pacific/Kiritimati'
);

INSERT INTO public.sessions (
  session_id, user_id, session_type, started_at, last_activity_at
)
VALUES (
  '13000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  'structured_problem_solving',
  statement_timestamp() - interval '4 hours',
  statement_timestamp() - interval '3 hours'
);

DO $$
DECLARE
  document JSONB;
BEGIN
  document := public.get_dashboard_snapshot('10000000-0000-0000-0000-000000000001');
  IF document IS NULL OR document->>'snapshot_version' IS NULL THEN
    RAISE EXCEPTION 'snapshot metadata missing';
  END IF;
  IF (document#>>'{progress,total}')::INT <> 2
    OR (document#>>'{progress,completed}')::INT <> 1
  THEN
    RAISE EXCEPTION 'today population and progress diverged';
  END IF;
  IF jsonb_array_length(document#>'{tasks,inbox}') <> 1
    OR jsonb_array_length(document#>'{tasks,carried_over}') <> 1
  THEN
    RAISE EXCEPTION 'task populations are inconsistent';
  END IF;
  IF document::TEXT LIKE '%Other tenant%' THEN
    RAISE EXCEPTION 'cross-tenant row leaked into snapshot';
  END IF;
  IF document#>>'{reminders,0,task,population}' <> 'carried_over'
    OR document#>>'{reminders,0,delivery_state}' <> 'overdue'
  THEN
    RAISE EXCEPTION 'Reminder presentation is incomplete';
  END IF;
  IF document#>>'{sessions,0,state}' <> 'inactive'
    OR document#>>'{sessions,0,session_type_label}' <> 'Structured Problem Solving'
  THEN
    RAISE EXCEPTION 'Session presentation is not customer-readable';
  END IF;
END;
$$;

SET ROLE authenticated;
DO $$
BEGIN
  BEGIN
    PERFORM public.get_dashboard_snapshot('10000000-0000-0000-0000-000000000001');
    RAISE EXCEPTION 'authenticated role unexpectedly called snapshot function';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
END;
$$;
RESET ROLE;
