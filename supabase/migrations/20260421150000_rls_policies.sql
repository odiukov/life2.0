-- Enable Row Level Security + tenant_isolation policies as defense-in-depth.
-- Backend uses service_role (prod) / postgres superuser (dev), both of which
-- bypass RLS. Policies fire for any accidental PostgREST/Dashboard access.
--
-- DEV SHIM: plain docker postgres has no auth schema/uid() function. The
-- block below creates a no-op auth.uid() that returns NULL when missing;
-- Supabase's real auth.uid() overrides this at cutover (CREATE OR REPLACE
-- in the auth schema is controlled by Supabase migrations, not ours).

DO $shim$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth') THEN
    CREATE SCHEMA auth;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname='auth' AND p.proname='uid'
  ) THEN
    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $fn$
      SELECT NULL::uuid
    $fn$;
  END IF;
  -- Grant the authenticated role exists; create as a no-op in dev if not.
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
    CREATE ROLE authenticated NOINHERIT;
  END IF;
END
$shim$;

DO $enable$
DECLARE
  t text;
  tables text[] := ARRAY[
    'health_logs','sleep_session','daily_stats','body_composition',
    'medications','habits',
    'finance_transactions','finance_category_cache',
    'alert_emissions',
    'integrations_credentials','oauth_state'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON public.%I FOR ALL TO authenticated USING (user_id = auth.uid())',
      t
    );
  END LOOP;
END
$enable$;
