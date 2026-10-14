"""Direct provider identities and application sessions.

Revision ID: c0007_auth
Revises: c0006_sync_rekey
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "c0007_auth"
down_revision: str | Sequence[str] | None = "c0006_sync_rekey"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    uuid = pg.UUID(as_uuid=True)
    tstz = pg.TIMESTAMP(timezone=True)
    user = lambda: sa.Column(
        "user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    op.create_table(
        "auth_identities",
        sa.Column("provider", sa.Text, primary_key=True),
        sa.Column("subject", sa.Text, primary_key=True),
        user(),
        sa.Column("email", sa.Text),
        sa.Column("created_at", tstz, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "provider", name="auth_identities_user_provider_key"),
    )
    op.create_table(
        "auth_flows",
        sa.Column("state_hash", sa.Text, primary_key=True),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("code_verifier", sa.Text, nullable=False),
        sa.Column("nonce", sa.Text, nullable=False),
        sa.Column("app_challenge", sa.Text, nullable=False),
        sa.Column("expires_at", tstz, nullable=False),
    )
    op.create_table(
        "auth_tickets",
        sa.Column("ticket_hash", sa.Text, primary_key=True),
        user(),
        sa.Column("app_challenge", sa.Text, nullable=False),
        sa.Column("expires_at", tstz, nullable=False),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", uuid, primary_key=True),
        user(),
        sa.Column("refresh_hash", sa.Text, nullable=False),
        sa.Column("expires_at", tstz, nullable=False),
        sa.Column("revoked_at", tstz),
    )
    op.create_index("auth_sessions_user_idx", "auth_sessions", ["user_id"])
    for table in ("auth_identities", "auth_flows", "auth_tickets", "auth_sessions"):
        op.execute(f"REVOKE ALL ON {table} FROM app_rw")


def downgrade() -> None:
    op.drop_index("auth_sessions_user_idx", table_name="auth_sessions")
    for table in ("auth_sessions", "auth_tickets", "auth_flows", "auth_identities"):
        op.drop_table(table)
