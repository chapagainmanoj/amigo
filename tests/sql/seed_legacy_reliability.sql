INSERT INTO public.user_profiles (user_id, telegram_chat_id, name, timezone)
VALUES ('11111111-1111-4111-8111-111111111111', 110011, 'Legacy', 'UTC');

INSERT INTO public.tasks (task_id, user_id, title, status)
VALUES (
  '22222222-2222-4222-8222-222222222222',
  '11111111-1111-4111-8111-111111111111',
  'Legacy task',
  'pending'
);

INSERT INTO public.reminders (
  reminder_id,
  task_id,
  user_id,
  scheduled_time,
  status,
  intended_local_date,
  intended_local_time,
  intended_timezone
)
VALUES (
  '33333333-3333-4333-8333-333333333333',
  '22222222-2222-4222-8222-222222222222',
  '11111111-1111-4111-8111-111111111111',
  now() + interval '2 hours',
  'pending',
  (now() + interval '2 hours')::date,
  (now() + interval '2 hours')::time,
  'UTC'
);
