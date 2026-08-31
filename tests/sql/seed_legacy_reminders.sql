\set ON_ERROR_STOP on

INSERT INTO public.user_profiles(user_id, telegram_chat_id, name)
VALUES (
  'dddddddd-0000-0000-0000-000000000004',
  4004,
  'Migration 006 backfill fixture'
);

INSERT INTO public.tasks(task_id, user_id, title, status)
VALUES (
  'dddddddd-4000-0000-0000-000000000004',
  'dddddddd-0000-0000-0000-000000000004',
  'Legacy reminder task',
  'pending'
);

INSERT INTO public.reminders(
  reminder_id,
  task_id,
  user_id,
  scheduled_time,
  status,
  created_at
)
VALUES
  (
    'dddddddd-5000-0000-0000-000000000004',
    'dddddddd-4000-0000-0000-000000000004',
    'dddddddd-0000-0000-0000-000000000004',
    now() + INTERVAL '1 hour',
    'pending',
    now() - INTERVAL '1 hour'
  ),
  (
    'dddddddd-5000-0000-0000-000000000005',
    'dddddddd-4000-0000-0000-000000000004',
    'dddddddd-0000-0000-0000-000000000004',
    now() + INTERVAL '2 hours',
    'sent',
    now()
  );
