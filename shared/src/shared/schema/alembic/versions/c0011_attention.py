"""Per-user dismissals of attention items ("hide until tomorrow").

Revision ID: c0011_attention
Revises: c0010_chat
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c0011_attention"
down_revision: str | Sequence[str] | None = "c0010_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = "NULLIF(current_setting('app.user_id', true), '')::uuid"


def _if_legacy(sql: str) -> str:
    """Skip grants for the retired role on fresh installations."""
    return f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_legacy') THEN {sql}; END IF; END $$"


def upgrade() -> None:
    op.execute(
        """CREATE TABLE attention_dismissals (
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        item_id text NOT NULL,
        until_date date NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT attention_dismissals_pkey PRIMARY KEY (user_id, item_id))"""
    )
    op.execute(_if_legacy("REVOKE ALL ON attention_dismissals FROM app_legacy"))
    op.execute("ALTER TABLE attention_dismissals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE attention_dismissals FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON attention_dismissals "
        f"USING (user_id = {TENANT}) WITH CHECK (user_id = {TENANT})"
    )


def downgrade() -> None:
    op.execute("DROP TABLE attention_dismissals")
