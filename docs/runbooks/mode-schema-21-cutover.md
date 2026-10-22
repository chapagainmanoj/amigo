# Operator cutover: Mode schema16 to21

Review-only instructions; no migration in this repository has been applied to Supabase by the
builder. The owner runs this procedure after review. Target schema is21, matching the backend.
The application and workers stay stopped during the maintenance window.

## Preflight

Use the intended database's operator session. Confirm its current approved001–016 ledger and
schema16. Before applying017, this count must be zero:

```sql
SELECT count(*) FROM public.mode_handoffs WHERE resolution = 'confirmed';
```

Every non-null profile timezone must be a PostgreSQL timezone name. This query must return no rows:

```sql
SELECT DISTINCT u.timezone
FROM public.user_profiles AS u
WHERE u.timezone IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_timezone_names AS z WHERE z.name = u.timezone
  );
```

Inspect/fix an unexpected result through an owner-reviewed data action before continuing; this
runbook does not grant the builder permission to change production data. Confirm the reviewed
release commit, the approved migration hashes, backup/restore readiness and that webhook/worker
processes are stopped. Run the complete local CI SQL chain and schema/lock-order probes first.

## One database session, all five migrations

Run from the repository root in one operator `psql` session. Stop on any error, and verify each
reported version before the next migration. Each migration owns its transaction and ledger guard.

```sql
\set ON_ERROR_STOP on
\i migrations/017_mode_conversations.sql
SELECT public.get_app_schema_version(); -- must be17
\i migrations/018_coaching_programs.sql
SELECT public.get_app_schema_version(); -- must be18
\i migrations/019_proactive_delivery_budget.sql
SELECT public.get_app_schema_version(); -- must be19
\i migrations/020_durable_memory.sql
SELECT public.get_app_schema_version(); -- must be20
\i migrations/021_confirmed_mode_suggestions.sql
SELECT public.get_app_schema_version(); -- must be21
```

Do not run only017–019: the matching application requires exact schema21. If a step fails, keep
maintenance active and obtain operator review of the actual schema/ledger before resuming. Do not
start a mismatched backend or invent a destructive rollback.

## Matching application and Telegram setting

Deploy the reviewed matching HEAD immediately after all five steps report the expected versions,
then verify the exact-version startup gate and the operator's staged functional checks. This
runbook does not authorize the builder to deploy or apply SQL.

Keep the production bot's Threaded Mode **off** until the owner chooses to enable it after this
application is reviewed and deployed. Topics-off uses `/mode`, `/mode <id>` and `/daily`; it does
not block startup. If enabled, also turn **Allow users to create new threads off** in BotFather.
Every send to a topics-enabled chat must have an explicit conversation. Android remains untested;
the owner's spike passed on Desktop and iOS only.

New Mode, Memory and suggestion admission stays gated by its own current evidence/consent; a
schema cutover or a successful process start does not enable these features. Participant-requested
Reminders, Later and the Activation test are outside the proactive-message budget.
