BEGIN;

CREATE OR REPLACE FUNCTION public.move_task_planning_day_command(
  p_user_id UUID,
  p_idempotency_key TEXT,
  p_payload_hash TEXT,
  p_task_id UUID,
  p_due_date DATE,
  p_expected_version BIGINT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  existing_receipt public.command_receipts%ROWTYPE;
  task_row public.tasks%ROWTYPE;
  command_result JSONB;
BEGIN
  IF p_user_id IS NULL OR NOT EXISTS (
    SELECT 1
    FROM public.user_profiles AS profile
    WHERE profile.user_id = p_user_id
  ) THEN
    RAISE EXCEPTION 'user_not_found';
  END IF;

  IF p_idempotency_key IS NULL
    OR length(btrim(p_idempotency_key)) NOT BETWEEN 1 AND 200
  THEN
    RAISE EXCEPTION 'invalid_idempotency_key';
  END IF;

  IF p_payload_hash IS NULL OR p_payload_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid_payload_hash';
  END IF;

  IF p_due_date IS NULL THEN
    RAISE EXCEPTION 'invalid_planning_day';
  END IF;

  IF p_expected_version IS NOT NULL AND p_expected_version < 1 THEN
    RAISE EXCEPTION 'invalid_task_version';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtextextended(p_user_id::text || ':' || p_idempotency_key, 0)
  );

  SELECT receipt.*
  INTO existing_receipt
  FROM public.command_receipts AS receipt
  WHERE receipt.user_id = p_user_id
    AND receipt.idempotency_key = p_idempotency_key;

  IF FOUND THEN
    IF existing_receipt.payload_hash <> p_payload_hash THEN
      RAISE EXCEPTION 'idempotency_key_conflict';
    END IF;
    RETURN existing_receipt.result;
  END IF;

  PERFORM pg_advisory_xact_lock(hashtextextended(p_task_id::text, 0));

  SELECT task.*
  INTO task_row
  FROM public.tasks AS task
  WHERE task.task_id = p_task_id
    AND task.user_id = p_user_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'task_not_found';
  END IF;

  IF task_row.status <> 'pending' THEN
    RAISE EXCEPTION 'task_not_pending';
  END IF;

  IF p_expected_version IS NOT NULL
    AND task_row.version <> p_expected_version
  THEN
    RAISE EXCEPTION 'stale_task_version';
  END IF;

  UPDATE public.tasks
  SET
    due_date = p_due_date,
    version = version + 1
  WHERE task_id = p_task_id
  RETURNING * INTO task_row;

  command_result := jsonb_build_object('task', to_jsonb(task_row));

  INSERT INTO public.command_receipts (
    user_id,
    idempotency_key,
    command_type,
    payload_hash,
    result
  )
  VALUES (
    p_user_id,
    p_idempotency_key,
    'move_task_planning_day',
    p_payload_hash,
    command_result
  );

  RETURN command_result;
END;
$$;

REVOKE ALL ON FUNCTION public.move_task_planning_day_command(
  UUID, TEXT, TEXT, UUID, DATE, BIGINT
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.move_task_planning_day_command(
  UUID, TEXT, TEXT, UUID, DATE, BIGINT
) TO service_role;

COMMIT;
