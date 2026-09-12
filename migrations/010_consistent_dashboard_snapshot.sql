BEGIN;

CREATE OR REPLACE FUNCTION public.get_dashboard_snapshot(p_user_id UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
WITH participant AS (
  SELECT
    profile.user_id,
    COALESCE(NULLIF(profile.timezone, ''), 'UTC') AS timezone,
    COALESCE(profile.session_timeout_minutes, 120) AS session_timeout_minutes,
    statement_timestamp() AS generated_at
  FROM public.user_profiles AS profile
  WHERE profile.user_id = p_user_id
),
context AS (
  SELECT
    participant.*,
    (participant.generated_at AT TIME ZONE participant.timezone)::DATE AS planning_day
  FROM participant
),
owned_tasks AS (
  SELECT task.*
  FROM public.tasks AS task
  JOIN context ON context.user_id = task.user_id
),
today_tasks AS (
  SELECT task.*
  FROM owned_tasks AS task
  CROSS JOIN context
  WHERE task.due_date = context.planning_day
),
snapshot AS (
  SELECT jsonb_build_object(
    'snapshot_version', gen_random_uuid(),
    'generated_at', context.generated_at,
    'timezone', context.timezone,
    'planning_day', context.planning_day,
    'tasks', jsonb_build_object(
      'today', COALESCE((
        SELECT jsonb_agg(to_jsonb(task) ORDER BY task.created_at DESC, task.task_id)
        FROM today_tasks AS task
      ), '[]'::JSONB),
      'inbox', COALESCE((
        SELECT jsonb_agg(to_jsonb(task) ORDER BY task.created_at DESC, task.task_id)
        FROM owned_tasks AS task
        WHERE task.due_date IS NULL AND task.status = 'pending'
      ), '[]'::JSONB),
      'carried_over', COALESCE((
        SELECT jsonb_agg(to_jsonb(task) ORDER BY task.due_date, task.created_at DESC, task.task_id)
        FROM owned_tasks AS task
        WHERE task.due_date < context.planning_day AND task.status = 'pending'
      ), '[]'::JSONB)
    ),
    'progress', jsonb_build_object(
      'completed', (SELECT count(*) FROM today_tasks WHERE status = 'completed'),
      'total', (SELECT count(*) FROM today_tasks)
    ),
    'reminders', COALESCE((
      SELECT jsonb_agg(
        to_jsonb(reminder) || jsonb_build_object(
          'task', jsonb_build_object(
            'task_id', task.task_id,
            'title', task.title,
            'category', task.category,
            'version', task.version,
            'population', CASE
              WHEN task.due_date = context.planning_day THEN 'today'
              WHEN task.due_date IS NULL THEN 'inbox'
              WHEN task.due_date < context.planning_day THEN 'carried_over'
              ELSE 'future'
            END
          ),
          'delivery_state', CASE
            WHEN reminder.status = 'pending' AND reminder.scheduled_time < context.generated_at
              THEN 'overdue'
            WHEN reminder.status = 'pending' THEN 'scheduled'
            WHEN reminder.status = 'sending' THEN 'delivering'
            ELSE 'delivered'
          END
        ) ORDER BY reminder.scheduled_time, reminder.reminder_id
      )
      FROM public.reminders AS reminder
      JOIN owned_tasks AS task ON task.task_id = reminder.task_id
      WHERE reminder.user_id = context.user_id
        AND task.user_id = context.user_id
        AND reminder.status IN ('pending', 'sending', 'sent')
    ), '[]'::JSONB),
    'sessions', COALESCE((
      SELECT jsonb_agg(session_row.payload ORDER BY session_row.started_at DESC)
      FROM (
        SELECT
          session.started_at,
          to_jsonb(session) || jsonb_build_object(
            'state', CASE
              WHEN session.ended_at IS NOT NULL THEN 'ended'
              WHEN session.last_activity_at < context.generated_at
                - make_interval(mins => context.session_timeout_minutes) THEN 'inactive'
              ELSE 'active'
            END,
            'label', COALESCE(
              NULLIF(session.context_summary, ''),
              CASE
                WHEN session.ended_at IS NOT NULL THEN 'Conversation'
                WHEN session.last_activity_at < context.generated_at
                  - make_interval(mins => context.session_timeout_minutes)
                  THEN 'Inactive conversation'
                ELSE 'Current conversation'
              END
            ),
            'session_type_label', initcap(replace(COALESCE(session.session_type, 'casual'), '_', ' ')),
            'duration_minutes', GREATEST(0, round(extract(epoch FROM (
              COALESCE(session.ended_at, context.generated_at) - session.started_at
            )) / 60)::INT)
          ) AS payload
        FROM public.sessions AS session
        WHERE session.user_id = context.user_id
        ORDER BY session.started_at DESC
        LIMIT 5
      ) AS session_row
    ), '[]'::JSONB)
  ) AS document
  FROM context
)
SELECT snapshot.document
FROM snapshot;
$$;

REVOKE ALL ON FUNCTION public.get_dashboard_snapshot(UUID)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_dashboard_snapshot(UUID)
  TO service_role;

COMMIT;
