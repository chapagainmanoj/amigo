BEGIN;

REVOKE UPDATE, DELETE ON TABLE public.tasks FROM authenticated;
DROP POLICY IF EXISTS task_update_own ON public.tasks;
DROP POLICY IF EXISTS task_delete_own ON public.tasks;

CREATE OR REPLACE FUNCTION public.resolve_task_command(
  p_user_id UUID,
  p_idempotency_key TEXT,
  p_payload_hash TEXT,
  p_task_id UUID,
  p_outcome public.task_status,
  p_expected_version BIGINT,
  p_acted_reminder_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  existing_receipt public.command_receipts%ROWTYPE;
  task_row public.tasks%ROWTYPE;
  acted_reminder public.reminders%ROWTYPE;
  active_reminder public.reminders%ROWTYPE;
  effect_id UUID;
  changed_reminders JSONB := '[]'::JSONB;
  effect_summaries JSONB := '[]'::JSONB;
  command_result JSONB;
BEGIN
  IF p_idempotency_key IS NULL
    OR length(btrim(p_idempotency_key)) NOT BETWEEN 1 AND 200
  THEN
    RAISE EXCEPTION 'invalid_idempotency_key';
  END IF;
  IF p_payload_hash IS NULL OR p_payload_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'invalid_payload_hash';
  END IF;
  IF p_outcome IS NULL OR p_outcome NOT IN ('completed', 'skipped', 'cancelled') THEN
    RAISE EXCEPTION 'invalid_task_outcome';
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

  IF p_acted_reminder_id IS NOT NULL THEN
    SELECT reminder.*
    INTO acted_reminder
    FROM public.reminders AS reminder
    WHERE reminder.reminder_id = p_acted_reminder_id
      AND reminder.task_id = p_task_id
      AND reminder.user_id = p_user_id
    FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'reminder_not_found';
    END IF;
  END IF;

  IF p_expected_version IS NOT NULL
    AND task_row.version <> p_expected_version
  THEN
    RAISE EXCEPTION 'stale_task_version';
  END IF;

  IF task_row.status <> 'pending' THEN
    IF task_row.status <> p_outcome THEN
      RAISE EXCEPTION 'task_already_resolved';
    END IF;

    command_result := jsonb_build_object(
      'task', to_jsonb(task_row),
      'task_version', task_row.version,
      'reminders', changed_reminders,
      'transitioned', FALSE,
      'effect_state', 'none',
      'effects', effect_summaries
    );

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
      'resolve_task',
      p_payload_hash,
      command_result
    );

    RETURN command_result;
  END IF;

  UPDATE public.tasks
  SET
    status = p_outcome,
    actual_completion = CASE WHEN p_outcome = 'completed' THEN now() ELSE NULL END,
    version = version + 1
  WHERE task_id = p_task_id
  RETURNING * INTO task_row;

  FOR active_reminder IN
    SELECT reminder.*
    FROM public.reminders AS reminder
    WHERE reminder.task_id = p_task_id
      AND reminder.user_id = p_user_id
      AND reminder.status IN ('pending', 'sending', 'sent')
    FOR UPDATE
  LOOP
    UPDATE public.reminders
    SET
      status = CASE
        WHEN reminder_id = p_acted_reminder_id
          AND status IN ('sending', 'sent')
        THEN 'acknowledged'::public.reminder_status
        ELSE 'cancelled'::public.reminder_status
      END,
      version = version + 1
    WHERE reminder_id = active_reminder.reminder_id
    RETURNING * INTO active_reminder;

    changed_reminders := changed_reminders || jsonb_build_array(to_jsonb(active_reminder));

    INSERT INTO public.scheduler_outbox (
      effect_key,
      effect_type,
      user_id,
      task_id,
      reminder_id,
      payload
    )
    VALUES (
      'cancel:' || active_reminder.reminder_id::text,
      'cancel',
      p_user_id,
      p_task_id,
      active_reminder.reminder_id,
      '{}'::JSONB
    )
    ON CONFLICT (effect_key) DO UPDATE
      SET effect_key = EXCLUDED.effect_key
    RETURNING scheduler_outbox.effect_id INTO effect_id;

    effect_summaries := effect_summaries || jsonb_build_array(
      jsonb_build_object('effect_id', effect_id, 'effect_type', 'cancel')
    );
  END LOOP;

  command_result := jsonb_build_object(
    'task', to_jsonb(task_row),
    'task_version', task_row.version,
    'reminders', changed_reminders,
    'transitioned', TRUE,
    'effect_state', CASE
      WHEN jsonb_array_length(effect_summaries) > 0 THEN 'queued'
      ELSE 'none'
    END,
    'effects', effect_summaries
  );

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
    'resolve_task',
    p_payload_hash,
    command_result
  );

  RETURN command_result;
END;
$$;

REVOKE ALL ON FUNCTION public.resolve_task_command(
  UUID, TEXT, TEXT, UUID, public.task_status, BIGINT, UUID
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.resolve_task_command(
  UUID, TEXT, TEXT, UUID, public.task_status, BIGINT, UUID
) TO service_role;

COMMIT;
