# Review: Tenant Isolation Policies Migration 004

Status: approved
Reviewer: project owner
Prepared: 2026-08-30

## Purpose

The existing policies hide rows by `user_id`, but they do not constrain cross-table ownership.
An authenticated Participant A can currently create an A-owned Task that references Participant
B's Session and an A-owned Reminder that references Participant B's Task when those UUIDs are
known. Supabase-style default grants also leave more browser write capability than the current
dashboard needs.

This proposed migration replaces the broad policies and implicit grants with an explicit browser
contract:

- Anonymous clients receive no product-table access.
- Authenticated clients may read their Profile, Tasks, Reminders, Sessions, and Messages.
- The current dashboard may create/update/delete its own Tasks and update only scheduling fields
  on its own Reminders until the shared-command slices replace direct writes.
- Profile identity/internal fields, Reminder identity/ownership, feedback, usage events, and
  Pairing data remain backend-only.
- Task-to-Session and Reminder-to-Task relationships must have the same owner.

## Proposed migration

```sql
BEGIN;

REVOKE ALL ON TABLE
  public.user_profiles,
  public.tasks,
  public.reminders,
  public.sessions,
  public.messages,
  public.feedback,
  public.usage_events,
  public.pairing_tokens
FROM anon, authenticated;

GRANT SELECT ON TABLE public.user_profiles TO authenticated;

GRANT SELECT, DELETE ON TABLE public.tasks TO authenticated;
GRANT INSERT (
  user_id,
  title,
  category,
  due_date,
  suggested_time,
  status,
  created_date
) ON TABLE public.tasks TO authenticated;
GRANT UPDATE (
  title,
  category,
  due_date,
  suggested_time,
  actual_completion,
  status
) ON TABLE public.tasks TO authenticated;

GRANT SELECT ON TABLE public.reminders TO authenticated;
GRANT UPDATE (
  scheduled_time,
  status,
  snooze_count
) ON TABLE public.reminders TO authenticated;

GRANT SELECT ON TABLE public.sessions, public.messages TO authenticated;

GRANT ALL ON TABLE
  public.user_profiles,
  public.tasks,
  public.reminders,
  public.sessions,
  public.messages,
  public.feedback,
  public.usage_events,
  public.pairing_tokens
TO service_role;

DROP POLICY IF EXISTS "Users see own profile" ON public.user_profiles;
DROP POLICY IF EXISTS "Users update own profile" ON public.user_profiles;
DROP POLICY IF EXISTS "Users see own tasks" ON public.tasks;
DROP POLICY IF EXISTS "Users see own reminders" ON public.reminders;
DROP POLICY IF EXISTS "Users see own sessions" ON public.sessions;
DROP POLICY IF EXISTS "Users see own messages" ON public.messages;

CREATE POLICY profile_select_own
  ON public.user_profiles
  FOR SELECT
  TO authenticated
  USING (supabase_auth_id = auth.uid());

CREATE POLICY task_select_own
  ON public.tasks
  FOR SELECT
  TO authenticated
  USING (
    user_id = (
      SELECT profile.user_id
      FROM public.user_profiles AS profile
      WHERE profile.supabase_auth_id = auth.uid()
    )
  );

CREATE POLICY task_insert_own
  ON public.tasks
  FOR INSERT
  TO authenticated
  WITH CHECK (
    user_id = (
      SELECT profile.user_id
      FROM public.user_profiles AS profile
      WHERE profile.supabase_auth_id = auth.uid()
    )
    AND (
      source_session_id IS NULL
      OR EXISTS (
        SELECT 1
        FROM public.sessions AS session
        WHERE session.session_id = source_session_id
          AND session.user_id = tasks.user_id
      )
    )
  );

CREATE POLICY task_update_own
  ON public.tasks
  FOR UPDATE
  TO authenticated
  USING (
    user_id = (
      SELECT profile.user_id
      FROM public.user_profiles AS profile
      WHERE profile.supabase_auth_id = auth.uid()
    )
  )
  WITH CHECK (
    user_id = (
      SELECT profile.user_id
      FROM public.user_profiles AS profile
      WHERE profile.supabase_auth_id = auth.uid()
    )
    AND (
      source_session_id IS NULL
      OR EXISTS (
        SELECT 1
        FROM public.sessions AS session
        WHERE session.session_id = source_session_id
          AND session.user_id = tasks.user_id
      )
    )
  );

CREATE POLICY task_delete_own
  ON public.tasks
  FOR DELETE
  TO authenticated
  USING (
    user_id = (
      SELECT profile.user_id
      FROM public.user_profiles AS profile
      WHERE profile.supabase_auth_id = auth.uid()
    )
  );

CREATE POLICY reminder_select_own
  ON public.reminders
  FOR SELECT
  TO authenticated
  USING (
    user_id = (
      SELECT profile.user_id
      FROM public.user_profiles AS profile
      WHERE profile.supabase_auth_id = auth.uid()
    )
  );

CREATE POLICY reminder_update_own
  ON public.reminders
  FOR UPDATE
  TO authenticated
  USING (
    user_id = (
      SELECT profile.user_id
      FROM public.user_profiles AS profile
      WHERE profile.supabase_auth_id = auth.uid()
    )
  )
  WITH CHECK (
    user_id = (
      SELECT profile.user_id
      FROM public.user_profiles AS profile
      WHERE profile.supabase_auth_id = auth.uid()
    )
    AND EXISTS (
      SELECT 1
      FROM public.tasks AS task
      WHERE task.task_id = reminders.task_id
        AND task.user_id = reminders.user_id
    )
  );

CREATE POLICY session_select_own
  ON public.sessions
  FOR SELECT
  TO authenticated
  USING (
    user_id = (
      SELECT profile.user_id
      FROM public.user_profiles AS profile
      WHERE profile.supabase_auth_id = auth.uid()
    )
  );

CREATE POLICY message_select_own
  ON public.messages
  FOR SELECT
  TO authenticated
  USING (
    user_id = (
      SELECT profile.user_id
      FROM public.user_profiles AS profile
      WHERE profile.supabase_auth_id = auth.uid()
    )
    AND (
      session_id IS NULL
      OR EXISTS (
        SELECT 1
        FROM public.sessions AS session
        WHERE session.session_id = messages.session_id
          AND session.user_id = messages.user_id
      )
    )
  );

COMMIT;
```

## Review checklist

- [x] Confirm anonymous clients should have no product-table privileges.
- [x] Confirm Dashboard Accounts may read their own Profile but cannot update Profile columns
  directly from the browser during Internal Preflight.
- [x] Confirm the current dashboard temporarily retains direct own-Task select/create/update/delete
  privileges until the shared-command slice replaces them.
- [x] Confirm the current dashboard temporarily retains own-Reminder select and limited scheduling
  updates, but cannot insert/delete Reminders or rewrite identity, Task, or delivery fields.
- [x] Confirm feedback, usage events, Pairing tokens, and every other mutation remain backend-only.
- [x] Confirm Task-to-Session, Reminder-to-Task, and Message-to-Session relationships must share the
  same participant owner.

## Decision

Approved by the project owner on 2026-08-30. The reviewed SQL was copied to
`migrations/004_tenant_isolation_policies.sql` without semantic changes.
