"""Household-scoped integration credentials; per-user Home Assistant rows move into them.

Revision ID: c0008_household_credentials
Revises: c0007_auth
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "c0008_household_credentials"
down_revision: str | Sequence[str] | None = "c0007_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPED = "household_id = (SELECT public.current_household_id())"
REFUSE_PLAINTEXT = """
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM integrations_credentials WHERE service = 'ha' AND payload_enc IS NULL) THEN
    RAISE EXCEPTION 'plaintext Home Assistant credentials found: run make sync-reencrypt first';
  END IF;
END $$"""
ENSURE_HOUSEHOLDS = """
SELECT public.household_new_for(c.user_id, u.name, u.timezone)
FROM integrations_credentials c
JOIN users u ON u.id = c.user_id
LEFT JOIN household_members m ON m.user_id = c.user_id
WHERE c.service = 'ha' AND m.user_id IS NULL
"""
# The newest row wins when several members of one household connected HA. The sealed bytes move
# unchanged: the same SECRETS__KEY opens them and nothing binds a ciphertext to its row.
MOVE = """
INSERT INTO household_credentials (household_id, service, payload_enc, version, updated_by, updated_at)
SELECT DISTINCT ON (m.household_id) m.household_id, 'ha', c.payload_enc, 1, c.user_id,
       c.created_at
FROM integrations_credentials c
JOIN household_members m ON m.user_id = c.user_id
WHERE c.service = 'ha'
ORDER BY m.household_id, c.created_at DESC, c.id
"""


def _if_legacy(sql: str) -> str:
    """Skip grants for the retired role on fresh installations."""
    return f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_legacy') THEN {sql}; END IF; END $$"


def upgrade() -> None:
    uuid = pg.UUID(as_uuid=True)
    op.create_table(
        "household_credentials",
        sa.Column(
            "household_id", uuid, sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("service", sa.Text, nullable=False),
        sa.Column("payload_enc", sa.LargeBinary, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("updated_by", uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "updated_at",
            pg.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("household_id", "service", name="household_credentials_pkey"),
        sa.CheckConstraint("service IN ('ha')", name="household_credentials_service_check"),
    )
    op.execute("INSERT INTO household_tables VALUES ('household_credentials', false, NULL)")
    op.execute(_if_legacy("REVOKE ALL ON household_credentials FROM app_legacy"))
    # Migrations run as app_owner, which is subject to FORCE RLS: lift it for the move only.
    for table in ("integrations_credentials", "users"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
    op.execute(REFUSE_PLAINTEXT)
    op.execute(ENSURE_HOUSEHOLDS)
    op.execute(MOVE)
    # Generations survive disconnects, so old proposals cannot match a new connection.
    op.execute("CREATE SEQUENCE household_credentials_version_seq AS integer")
    op.execute("GRANT USAGE ON SEQUENCE household_credentials_version_seq TO app_rw")
    op.execute(
        _if_legacy("REVOKE ALL ON SEQUENCE household_credentials_version_seq FROM app_legacy")
    )
    op.execute(
        "SELECT setval('household_credentials_version_seq', COALESCE((SELECT max(version) FROM household_credentials), 1), EXISTS (SELECT 1 FROM household_credentials))"
    )
    op.execute("DELETE FROM integrations_credentials WHERE service = 'ha'")
    for table in ("integrations_credentials", "users"):
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE household_credentials ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY household_scope ON household_credentials USING ({SCOPED}) WITH CHECK ({SCOPED})"
    )
    op.execute(
        "ALTER TABLE integrations_credentials DROP CONSTRAINT integrations_credentials_service_check"
    )
    op.execute(
        "ALTER TABLE integrations_credentials ADD CONSTRAINT integrations_credentials_service_check "
        "CHECK (service IN ('yazio', 'google_calendar', 'garmin'))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE integrations_credentials DROP CONSTRAINT integrations_credentials_service_check"
    )
    op.execute(
        "ALTER TABLE integrations_credentials ADD CONSTRAINT integrations_credentials_service_check "
        "CHECK (service IN ('ha', 'yazio', 'google_calendar', 'garmin'))"
    )
    op.execute("DELETE FROM household_tables WHERE table_name = 'household_credentials'")
    op.drop_table("household_credentials")
    op.execute("DROP SEQUENCE household_credentials_version_seq")
