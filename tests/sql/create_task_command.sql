\set ON_ERROR_STOP on

SET ROLE service_role;

DO $$
DECLARE
  first_result JSONB;
  replay_result JSONB;
  task_count_before INTEGER;
BEGIN
  SELECT count(*) INTO task_count_before FROM public.tasks;

  first_result := public.create_task_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-create-task-request-1',
    repeat('a', 64),
    'SQL Inbox Task',
    'other',
    NULL,
    NULL
  );
  replay_result := public.create_task_command(
    'aaaaaaaa-0000-0000-0000-000000000001',
    'sql-create-task-request-1',
    repeat('a', 64),
    'SQL Inbox Task',
    'other',
    NULL,
    NULL
  );

  IF replay_result <> first_result THEN
    RAISE EXCEPTION 'Create Task replay did not return the stored result';
  END IF;
  IF (SELECT count(*) FROM public.tasks) <> task_count_before + 1 THEN
    RAISE EXCEPTION 'Create Task replay created a duplicate';
  END IF;
  IF (SELECT count(*) FROM public.command_receipts) <> 1 THEN
    RAISE EXCEPTION 'Create Task replay created an invalid receipt population';
  END IF;
  IF (first_result #>> '{task,status}') <> 'pending'
    OR first_result #> '{task,due_date}' <> 'null'::JSONB
  THEN
    RAISE EXCEPTION 'Create Task did not produce a pending Inbox Task';
  END IF;

  BEGIN
    PERFORM public.create_task_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-create-task-request-1',
      repeat('b', 64),
      'Conflicting Task',
      'other',
      NULL,
      NULL
    );
    RAISE EXCEPTION 'Conflicting idempotency payload succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'idempotency_key_conflict' THEN
        RAISE;
      END IF;
  END;

  BEGIN
    PERFORM public.create_task_command(
      'aaaaaaaa-0000-0000-0000-000000000001',
      'sql-create-task-request-2',
      repeat('c', 64),
      'Cross-linked Task',
      'other',
      NULL,
      'bbbbbbbb-3000-0000-0000-000000000002'
    );
    RAISE EXCEPTION 'Cross-tenant Task-to-Session link succeeded';
  EXCEPTION
    WHEN raise_exception THEN
      IF SQLERRM <> 'session_not_found' THEN
        RAISE;
      END IF;
  END;

  IF (SELECT count(*) FROM public.tasks) <> task_count_before + 1 THEN
    RAISE EXCEPTION 'Rejected Create Task command mutated Tasks';
  END IF;
END;
$$;

RESET ROLE;
SET ROLE authenticated;

DO $$
BEGIN
  IF has_table_privilege(current_user, 'public.tasks', 'INSERT') THEN
    RAISE EXCEPTION 'Authenticated role retained direct Task INSERT';
  END IF;
  IF has_table_privilege(current_user, 'public.command_receipts', 'SELECT') THEN
    RAISE EXCEPTION 'Authenticated role can read command receipts';
  END IF;
  IF has_function_privilege(
    current_user,
    'public.create_task_command(uuid,text,text,text,task_category,date,uuid)',
    'EXECUTE'
  ) THEN
    RAISE EXCEPTION 'Authenticated role can execute Create Task RPC';
  END IF;
END;
$$;

RESET ROLE;
