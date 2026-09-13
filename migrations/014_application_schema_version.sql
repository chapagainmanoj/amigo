BEGIN;

CREATE TABLE public.schema_migrations (
  version INT PRIMARY KEY CHECK (version > 0),
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;

-- service_role must be revoked by name. The Supabase role bootstrap grants it DML on every
-- new table in public, so a REVOKE that omits it leaves the application's own credential able to
-- rewrite the ledger its startup gate is decided by.
REVOKE ALL ON TABLE public.schema_migrations FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.schema_migrations TO service_role;

-- The recorded chain revision must be earned, not asserted. Each prior migration is
-- represented by an object only that migration creates; a chain missing any of them
-- fails here rather than reporting a version the database does not actually have.
DO $$
DECLARE
  expected CONSTANT TEXT[][] := ARRAY[
    ['1',  'table',    'public.user_profiles'],
    ['2',  'table',    'public.pairing_tokens'],
    ['3',  'function', 'public.complete_pairing'],
    ['4',  'policy',   'public.tasks.task_select_own'],
    ['5',  'function', 'public.create_task_command'],
    ['6',  'function', 'public.claim_scheduler_outbox'],
    ['7',  'function', 'public.resolve_task_command'],
    ['8',  'function', 'public.apply_later_command'],
    ['9',  'function', 'public.claim_telegram_update'],
    ['10', 'function', 'public.get_dashboard_snapshot'],
    ['11', 'function', 'public.get_reminder_reliability_health'],
    ['12', 'function', 'public.move_task_planning_day_command'],
    ['13', 'function', 'public.get_activation_state']
  ];
  entry TEXT[];
  present BOOLEAN;
BEGIN
  FOREACH entry SLICE 1 IN ARRAY expected
  LOOP
    present := CASE entry[2]
      WHEN 'table' THEN to_regclass(entry[3]) IS NOT NULL
      WHEN 'function' THEN EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc AS proc
        JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = proc.pronamespace
        WHERE namespace.nspname || '.' || proc.proname = entry[3]
      )
      WHEN 'policy' THEN EXISTS (
        SELECT 1 FROM pg_catalog.pg_policies
        WHERE schemaname || '.' || tablename || '.' || policyname = entry[3]
      )
      -- A verification loop must never default to "applied" for an unhandled kind.
      ELSE FALSE
    END;

    IF NOT present THEN
      RAISE EXCEPTION
        'migration % is not applied: missing % %', entry[1], entry[2], entry[3];
    END IF;

    INSERT INTO public.schema_migrations (version) VALUES (entry[1]::INT);
  END LOOP;

  INSERT INTO public.schema_migrations (version) VALUES (14);
END;
$$;

CREATE OR REPLACE FUNCTION public.get_app_schema_version()
RETURNS INT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT max(version) FROM public.schema_migrations;
$$;

REVOKE ALL ON FUNCTION public.get_app_schema_version() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_app_schema_version() TO service_role;

COMMIT;
