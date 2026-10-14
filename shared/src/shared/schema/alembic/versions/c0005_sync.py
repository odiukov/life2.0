"""Encrypted integration credentials, per-user sync state and the sync scheduling functions.

Revision ID: c0005_sync
Revises: c0004_notifications
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "c0005_sync"
down_revision: str | Sequence[str] | None = "c0004_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSTZ = pg.TIMESTAMP(timezone=True)
TENANT = "NULLIF(current_setting('app.user_id', true), '')::uuid"
OLD_CHECK = "(secret_id IS NOT NULL)::int + (payload_dev IS NOT NULL)::int = 1"
NEW_CHECK = "(secret_id IS NOT NULL)::int + (payload_dev IS NOT NULL)::int + (payload_enc IS NOT NULL)::int = 1"
DUE = """
CREATE FUNCTION integration_users_due(p_now timestamptz, p_hour int)
RETURNS TABLE(user_id uuid, services text[], timezone text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT c.user_id, array_agg(c.service ORDER BY c.service), COALESCE(tz.name, 'UTC')
  FROM integrations_credentials c
  JOIN users u ON u.id = c.user_id
  LEFT JOIN pg_catalog.pg_timezone_names tz ON tz.name = u.timezone
  LEFT JOIN integration_sync_state s ON s.user_id = c.user_id AND s.service = c.service
  WHERE c.service IN ('garmin', 'yazio')
    AND extract(hour FROM (p_now AT TIME ZONE COALESCE(tz.name, 'UTC'))) >= p_hour
    AND (s.last_success_at IS NULL
         OR (s.last_success_at AT TIME ZONE COALESCE(tz.name, 'UTC'))::date
            < (p_now AT TIME ZONE COALESCE(tz.name, 'UTC'))::date)
    AND (s.last_attempt_at IS NULL OR s.last_attempt_at <= p_now - interval '1 hour')
    AND NOT (s.last_error IS NOT DISTINCT FROM 'auth_failed'
             AND (s.last_attempt_at AT TIME ZONE COALESCE(tz.name, 'UTC'))::date
                 = (p_now AT TIME ZONE COALESCE(tz.name, 'UTC'))::date)
  GROUP BY c.user_id, tz.name
$$"""
PLAINTEXT = """
CREATE FUNCTION credentials_plaintext() RETURNS TABLE(user_id uuid, service text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT user_id, service FROM integrations_credentials WHERE payload_dev IS NOT NULL ORDER BY user_id, service
$$"""


def upgrade() -> None:
    op.add_column("integrations_credentials", sa.Column("payload_enc", sa.LargeBinary))
    op.drop_constraint(
        "integrations_credentials_one_backend_check", "integrations_credentials", type_="check"
    )
    op.create_check_constraint(
        "integrations_credentials_one_backend_check", "integrations_credentials", NEW_CHECK
    )
    op.create_table(
        "integration_sync_state",
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("service", sa.Text, nullable=False),
        sa.Column("last_attempt_at", TSTZ),
        sa.Column("last_success_at", TSTZ),
        sa.Column("last_error", sa.Text),
        sa.PrimaryKeyConstraint("user_id", "service", name="integration_sync_state_pkey"),
        sa.CheckConstraint(
            "service IN ('garmin', 'yazio')", name="integration_sync_state_service_check"
        ),
    )
    op.execute("ALTER TABLE integration_sync_state ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE integration_sync_state FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON integration_sync_state USING (user_id = {TENANT}) WITH CHECK (user_id = {TENANT})"
    )
    # The scheduling functions run as app_owner, which FORCE RLS filters too: allow it to read.
    for table in ("integrations_credentials", "users", "integration_sync_state"):
        op.execute(f"CREATE POLICY owner_jobs_read ON {table} FOR SELECT TO app_owner USING (true)")
    op.execute(DUE)
    op.execute(PLAINTEXT)
    for signature in ("integration_users_due(timestamptz, int)", "credentials_plaintext()"):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO app_rw")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS credentials_plaintext()")
    op.execute("DROP FUNCTION IF EXISTS integration_users_due(timestamptz, int)")
    for table in ("integrations_credentials", "users"):
        op.execute(f"DROP POLICY IF EXISTS owner_jobs_read ON {table}")
    op.drop_table("integration_sync_state")
    op.drop_constraint(
        "integrations_credentials_one_backend_check", "integrations_credentials", type_="check"
    )
    # The owner must remove sealed rows without a tenant during rollback.
    op.execute("ALTER TABLE integrations_credentials NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM integrations_credentials WHERE payload_enc IS NOT NULL")
    op.execute("ALTER TABLE integrations_credentials FORCE ROW LEVEL SECURITY")
    op.create_check_constraint(
        "integrations_credentials_one_backend_check", "integrations_credentials", OLD_CHECK
    )
    op.drop_column("integrations_credentials", "payload_enc")
