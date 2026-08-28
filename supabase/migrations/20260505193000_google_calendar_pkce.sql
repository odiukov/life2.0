-- Store the per-request PKCE verifier for Google Calendar OAuth callbacks.
ALTER TABLE public.oauth_state
  ADD COLUMN IF NOT EXISTS code_verifier text;
