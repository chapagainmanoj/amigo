\set ON_ERROR_STOP on

INSERT INTO public.user_profiles(user_id, telegram_chat_id, name)
VALUES (
  'cccccccc-0000-0000-0000-000000000003',
  3003,
  'Migration 005 backfill fixture'
);

INSERT INTO public.tasks(user_id, title, status)
VALUES
  ('cccccccc-0000-0000-0000-000000000003', 'Legacy done', 'done'),
  ('cccccccc-0000-0000-0000-000000000003', 'Legacy deferred', 'deferred'),
  ('cccccccc-0000-0000-0000-000000000003', 'Legacy skipped', 'skipped');
