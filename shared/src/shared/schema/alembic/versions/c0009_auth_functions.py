"""Sign-in functions: app_rw reaches the auth_* tables only through these.

Revision ID: c0009_auth_functions
Revises: c0008_household_credentials
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c0009_auth_functions"
down_revision: str | Sequence[str] | None = "c0008_household_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFINER = "SECURITY DEFINER SET search_path = public, pg_temp"
FUNCTIONS: dict[str, str] = {
    "auth_profile(uuid)": f"""
CREATE FUNCTION auth_profile(p_user uuid) RETURNS TABLE(out_name text, out_email text)
LANGUAGE plpgsql {DEFINER} AS $$
BEGIN
  -- users has FORCE RLS: read it as this user.
  PERFORM pg_catalog.set_config('app.user_id', p_user::text, true);
  RETURN QUERY SELECT u.name,
    (SELECT i.email FROM auth_identities i WHERE i.user_id = p_user ORDER BY i.created_at LIMIT 1)
    FROM users u WHERE u.id = p_user;
END $$""",
    "auth_begin_flow(text, text, text, text, text, integer)": f"""
CREATE FUNCTION auth_begin_flow(p_state text, p_provider text, p_verifier text, p_nonce text, p_challenge text, p_ttl_s integer)
RETURNS void LANGUAGE plpgsql {DEFINER} AS $$
BEGIN
  DELETE FROM auth_flows f WHERE f.expires_at < pg_catalog.now() - interval '1 hour';
  INSERT INTO auth_flows (state_hash, provider, code_verifier, nonce, app_challenge, expires_at)
    VALUES (p_state, p_provider, p_verifier, p_nonce, p_challenge, pg_catalog.now() + pg_catalog.make_interval(secs => p_ttl_s));
END $$""",
    "auth_take_flow(text, text)": f"""
CREATE FUNCTION auth_take_flow(p_state text, p_provider text)
RETURNS TABLE(out_verifier text, out_nonce text, out_challenge text) LANGUAGE sql {DEFINER} AS $$
  DELETE FROM auth_flows f WHERE f.state_hash = p_state AND f.provider = p_provider AND f.expires_at > pg_catalog.now()
  RETURNING f.code_verifier, f.nonce, f.app_challenge
$$""",
    "auth_link_identity(text, text, text, text)": f"""
CREATE FUNCTION auth_link_identity(p_provider text, p_subject text, p_email text, p_name text) RETURNS uuid
LANGUAGE plpgsql {DEFINER} AS $$
DECLARE uid uuid;
BEGIN
  -- Serialize first sign-ins for one provider subject.
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_provider || ':' || p_subject, 0));
  SELECT i.user_id INTO uid FROM auth_identities i WHERE i.provider = p_provider AND i.subject = p_subject;
  IF uid IS NOT NULL THEN RETURN uid; END IF;
  uid := pg_catalog.gen_random_uuid();
  PERFORM pg_catalog.set_config('app.user_id', uid::text, true);
  INSERT INTO users (id, name, timezone)
    VALUES (uid, COALESCE(NULLIF(p_name, ''), NULLIF(p_email, ''), pg_catalog.initcap(p_provider)), 'UTC');
  INSERT INTO auth_identities (provider, subject, user_id, email) VALUES (p_provider, p_subject, uid, p_email);
  RETURN uid;
END $$""",
    "auth_issue_ticket(text, uuid, text, integer)": f"""
CREATE FUNCTION auth_issue_ticket(p_ticket text, p_user uuid, p_challenge text, p_ttl_s integer)
RETURNS void LANGUAGE plpgsql {DEFINER} AS $$
BEGIN
  DELETE FROM auth_tickets t WHERE t.expires_at < pg_catalog.now() - interval '1 hour';
  INSERT INTO auth_tickets (ticket_hash, user_id, app_challenge, expires_at)
    VALUES (p_ticket, p_user, p_challenge, pg_catalog.now() + pg_catalog.make_interval(secs => p_ttl_s));
END $$""",
    "auth_exchange_ticket(text, text, uuid, text, integer)": f"""
CREATE FUNCTION auth_exchange_ticket(p_ticket text, p_challenge text, p_session uuid, p_refresh text, p_ttl_s integer)
RETURNS TABLE(out_user uuid, out_name text, out_email text) LANGUAGE plpgsql {DEFINER} AS $$
DECLARE uid uuid;
BEGIN
  DELETE FROM auth_tickets t
    WHERE t.ticket_hash = p_ticket AND t.app_challenge = p_challenge AND t.expires_at > pg_catalog.now()
    RETURNING t.user_id INTO uid;
  IF uid IS NULL THEN RETURN; END IF;
  INSERT INTO auth_sessions (id, user_id, refresh_hash, expires_at)
    VALUES (p_session, uid, p_refresh, pg_catalog.now() + pg_catalog.make_interval(secs => p_ttl_s));
  RETURN QUERY SELECT uid, p.out_name, p.out_email FROM auth_profile(uid) p;
END $$""",
    "auth_rotate_session(uuid, text, text, integer)": f"""
CREATE FUNCTION auth_rotate_session(p_session uuid, p_presented text, p_new text, p_ttl_s integer)
RETURNS TABLE(out_status text, out_user uuid, out_name text, out_email text) LANGUAGE plpgsql {DEFINER} AS $$
DECLARE s record;
BEGIN
  SELECT * INTO s FROM auth_sessions a WHERE a.id = p_session FOR UPDATE;
  IF NOT FOUND OR s.revoked_at IS NOT NULL OR s.expires_at <= pg_catalog.now() THEN
    RETURN QUERY SELECT 'expired'::text, NULL::uuid, NULL::text, NULL::text; RETURN;
  END IF;
  IF s.refresh_hash <> p_presented THEN
    -- A replayed refresh token: revoke the session (the caller commits; the client must sign in).
    UPDATE auth_sessions a SET revoked_at = pg_catalog.now() WHERE a.id = p_session;
    RETURN QUERY SELECT 'reused'::text, s.user_id, NULL::text, NULL::text; RETURN;
  END IF;
  UPDATE auth_sessions a SET refresh_hash = p_new, expires_at = pg_catalog.now() + pg_catalog.make_interval(secs => p_ttl_s)
    WHERE a.id = p_session;
  RETURN QUERY SELECT 'ok'::text, s.user_id, p.out_name, p.out_email FROM auth_profile(s.user_id) p;
END $$""",
    "auth_revoke_session(uuid)": f"""
CREATE FUNCTION auth_revoke_session(p_session uuid) RETURNS void LANGUAGE sql {DEFINER} AS $$
  UPDATE auth_sessions a SET revoked_at = pg_catalog.now() WHERE a.id = p_session AND a.revoked_at IS NULL
$$""",
    "auth_session_active(uuid, uuid)": f"""
CREATE FUNCTION auth_session_active(p_session uuid, p_user uuid) RETURNS boolean LANGUAGE sql STABLE {DEFINER} AS $$
  SELECT EXISTS (
    SELECT 1 FROM auth_sessions a
    WHERE a.id = p_session AND a.user_id = p_user AND a.revoked_at IS NULL AND a.expires_at > pg_catalog.now())
$$""",
}
INTERNAL = {"auth_profile(uuid)"}


def upgrade() -> None:
    for signature, body in FUNCTIONS.items():
        op.execute(body)
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        if signature not in INTERNAL:
            op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO app_rw")


def downgrade() -> None:
    for signature in reversed(list(FUNCTIONS)):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
