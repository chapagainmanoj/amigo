\set ON_ERROR_STOP on

DO $$
BEGIN
  IF (SELECT status::text FROM public.tasks WHERE title = 'Legacy done') <> 'completed' THEN
    RAISE EXCEPTION 'Migration 005 did not map done to completed';
  END IF;
  IF (SELECT status::text FROM public.tasks WHERE title = 'Legacy deferred') <> 'pending' THEN
    RAISE EXCEPTION 'Migration 005 did not map deferred to pending';
  END IF;
  IF (SELECT status::text FROM public.tasks WHERE title = 'Legacy skipped') <> 'skipped' THEN
    RAISE EXCEPTION 'Migration 005 changed skipped unexpectedly';
  END IF;
  IF (
    SELECT array_agg(enumlabel::text ORDER BY enumsortorder)
    FROM pg_enum
    WHERE enumtypid = 'public.task_status'::regtype
  ) <> ARRAY['pending', 'completed', 'skipped', 'cancelled'] THEN
    RAISE EXCEPTION 'Task lifecycle enum is not canonical';
  END IF;
END;
$$;

DELETE FROM public.tasks
WHERE user_id = 'cccccccc-0000-0000-0000-000000000003';

DELETE FROM public.user_profiles
WHERE user_id = 'cccccccc-0000-0000-0000-000000000003';
