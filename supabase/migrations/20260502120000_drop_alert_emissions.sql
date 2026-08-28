-- 0006: drop alert_emissions table (briefing-precompute removed).
BEGIN;

DROP TABLE IF EXISTS public.alert_emissions CASCADE;

COMMIT;
