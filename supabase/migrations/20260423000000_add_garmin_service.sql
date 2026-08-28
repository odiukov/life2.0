-- Allow 'garmin' as a service in integrations_credentials.
-- Needed for per-user Garmin Connect credential storage (multi-user sync).

ALTER TABLE public.integrations_credentials
  DROP CONSTRAINT IF EXISTS integrations_credentials_service_check;

ALTER TABLE public.integrations_credentials
  ADD CONSTRAINT integrations_credentials_service_check
  CHECK (service IN ('ha', 'yazio', 'google_calendar', 'garmin'));
