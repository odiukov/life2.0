-- Per-user, per-service credential storage.
--
-- Dual-backend design:
--   - prod (Supabase): secret_id references vault.secrets.id; payload_dev is NULL
--   - dev  (docker):   payload_dev holds the JSON plaintext; secret_id is NULL
-- A CHECK constraint enforces exactly-one. orchestrator/app/vault.py selects the
-- backend by env var VAULT_BACKEND=supabase|dev and writes to the matching column.
--
-- DEV NOTE: auth.users doesn't exist locally — FK targets public.users. At Supabase
-- cutover the FK is re-pointed at auth.users by a Phase-B migration.

CREATE TABLE IF NOT EXISTS public.integrations_credentials (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  service      text NOT NULL CHECK (service IN ('ha', 'yazio', 'google_calendar')),
  secret_id    uuid,           -- prod: FK into vault.secrets.id
  payload_dev  jsonb,          -- dev-mode plaintext fallback
  created_at   timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz,
  UNIQUE (user_id, service),
  CHECK ((secret_id IS NOT NULL)::int + (payload_dev IS NOT NULL)::int = 1)
);

CREATE INDEX IF NOT EXISTS integrations_credentials_user_idx
  ON public.integrations_credentials (user_id);

-- Short-lived CSRF-nonce table for Google Calendar OAuth (spec §4.5.2).
CREATE TABLE IF NOT EXISTS public.oauth_state (
  nonce      uuid PRIMARY KEY,
  user_id    uuid NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  service    text NOT NULL CHECK (service IN ('google_calendar')),
  created_at timestamptz NOT NULL DEFAULT now(),
  used_at    timestamptz
);
CREATE INDEX IF NOT EXISTS oauth_state_user_idx ON public.oauth_state (user_id);

CREATE OR REPLACE FUNCTION public.gc_oauth_state() RETURNS void LANGUAGE sql AS $$
  DELETE FROM public.oauth_state WHERE created_at < now() - interval '1 hour';
$$;
