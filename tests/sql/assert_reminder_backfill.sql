\set ON_ERROR_STOP on

DO $$
BEGIN
  IF (
    SELECT count(*)
    FROM public.reminders
    WHERE task_id = 'dddddddd-4000-0000-0000-000000000004'
      AND status IN ('pending', 'sending', 'sent')
  ) <> 1 THEN
    RAISE EXCEPTION 'Migration 006 did not retain exactly one active Reminder';
  END IF;

  IF (
    SELECT status::text
    FROM public.reminders
    WHERE reminder_id = 'dddddddd-5000-0000-0000-000000000004'
  ) <> 'cancelled' THEN
    RAISE EXCEPTION 'Migration 006 did not cancel the older active Reminder';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.reminders
    WHERE task_id = 'dddddddd-4000-0000-0000-000000000004'
      AND (
        intended_local_date IS NULL
        OR intended_local_time IS NULL
        OR intended_timezone IS NULL
      )
  ) THEN
    RAISE EXCEPTION 'Migration 006 left intended Reminder time incomplete';
  END IF;

  IF (
    SELECT array_agg(enumlabel::text ORDER BY enumsortorder)
    FROM pg_enum
    WHERE enumtypid = 'public.reminder_status'::regtype
  ) <> ARRAY[
    'pending',
    'sending',
    'sent',
    'acknowledged',
    'missed',
    'failed',
    'cancelled'
  ] THEN
    RAISE EXCEPTION 'Reminder lifecycle enum is not canonical';
  END IF;
END;
$$;

DELETE FROM public.reminders
WHERE task_id = 'dddddddd-4000-0000-0000-000000000004';

DELETE FROM public.tasks
WHERE task_id = 'dddddddd-4000-0000-0000-000000000004';

DELETE FROM public.user_profiles
WHERE user_id = 'dddddddd-0000-0000-0000-000000000004';
