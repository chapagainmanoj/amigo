\set ON_ERROR_STOP on

SET ROLE service_role;

DO $$
DECLARE
  reported INT;
BEGIN
  reported := public.get_app_schema_version();

  IF reported <> 14 THEN
    RAISE EXCEPTION 'Applied migration chain reported schema version %, expected 14', reported;
  END IF;

  -- The application's require_schema_version refuses anything that is not an exact
  -- integer, so the RPC must not return a string, numeric, or NULL.
  IF pg_typeof(public.get_app_schema_version()) <> 'integer'::regtype THEN
    RAISE EXCEPTION 'Schema version is not an exact integer';
  END IF;

  IF (SELECT count(*) FROM public.schema_migrations) <> 14
    OR (SELECT count(*) FROM public.schema_migrations WHERE version BETWEEN 1 AND 14) <> 14
  THEN
    RAISE EXCEPTION 'Schema ledger does not record every migration in the chain exactly once';
  END IF;

  IF EXISTS (
    SELECT 1 FROM generate_series(1, 14) AS expected(version)
    WHERE NOT EXISTS (
      SELECT 1 FROM public.schema_migrations AS applied
      WHERE applied.version = expected.version
    )
  ) THEN
    RAISE EXCEPTION 'Schema ledger has a gap in the applied migration chain';
  END IF;

END;
$$;

-- The application credential must not be able to rewrite the ledger its own startup gate reads.
DO $$
BEGIN
  IF has_table_privilege('service_role', 'public.schema_migrations', 'INSERT')
    OR has_table_privilege('service_role', 'public.schema_migrations', 'UPDATE')
    OR has_table_privilege('service_role', 'public.schema_migrations', 'DELETE')
  THEN
    RAISE EXCEPTION 'service_role can rewrite the schema ledger its startup gate depends on';
  END IF;
END;
$$;

DO $$
BEGIN
  BEGIN
    INSERT INTO public.schema_migrations (version) VALUES (99);
    RAISE EXCEPTION 'service_role inserted a schema ledger row';
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;
END;
$$;

RESET ROLE;

-- Ledger mutation is an owner-only operation, so these probes run as the migration owner.
DO $$
BEGIN
  -- A later migration must move the reported revision, so a database ahead of the
  -- application also fails the exact-version startup gate.
  INSERT INTO public.schema_migrations (version) VALUES (15);
  IF public.get_app_schema_version() <> 15 THEN
    RAISE EXCEPTION 'Schema version did not follow the applied chain forward';
  END IF;
  DELETE FROM public.schema_migrations WHERE version = 15;

  -- The revision is the highest applied migration, not a count of rows: a database
  -- carrying a non-contiguous later migration must report that migration's number.
  INSERT INTO public.schema_migrations (version) VALUES (20);
  IF public.get_app_schema_version() <> 20 THEN
    RAISE EXCEPTION 'Schema version is derived from a row count rather than the chain head';
  END IF;
  DELETE FROM public.schema_migrations WHERE version = 20;

  IF public.get_app_schema_version() <> 14 THEN
    RAISE EXCEPTION 'Schema version did not return to the real chain revision';
  END IF;
END;
$$;

SET ROLE service_role;

DO $$
DECLARE
  definer BOOLEAN;
  config TEXT[];
BEGIN
  SELECT proc.prosecdef, proc.proconfig
  INTO definer, config
  FROM pg_catalog.pg_proc AS proc
  JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = proc.pronamespace
  WHERE namespace.nspname = 'public'
    AND proc.proname = 'get_app_schema_version';

  IF NOT FOUND OR NOT definer THEN
    RAISE EXCEPTION 'Schema version function is not SECURITY DEFINER';
  END IF;
  IF config IS NULL OR NOT ('search_path=pg_catalog, public' = ANY(config)) THEN
    RAISE EXCEPTION 'Schema version function did not pin its search_path';
  END IF;
END;
$$;

RESET ROLE;
SET ROLE anon;

DO $$
BEGIN
  IF has_function_privilege(current_user, 'public.get_app_schema_version()', 'EXECUTE')
    OR has_table_privilege(current_user, 'public.schema_migrations', 'SELECT')
  THEN
    RAISE EXCEPTION 'Anonymous role retained schema-version access';
  END IF;
END;
$$;

RESET ROLE;
SET ROLE authenticated;

DO $$
BEGIN
  IF has_function_privilege(current_user, 'public.get_app_schema_version()', 'EXECUTE')
    OR has_table_privilege(current_user, 'public.schema_migrations', 'SELECT')
  THEN
    RAISE EXCEPTION 'Authenticated role retained schema-version access';
  END IF;
END;
$$;

RESET ROLE;
