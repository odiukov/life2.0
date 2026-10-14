"""Per-user notification inbox and device push tokens.

Revision ID: c0004_notifications
Revises: c0003_kitchen
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "c0004_notifications"
down_revision: str | Sequence[str] | None = "c0003_kitchen"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
TSTZ = pg.TIMESTAMP(timezone=True)
UUID = pg.UUID(as_uuid=True)
TENANT = "NULLIF(pg_catalog.current_setting('app.user_id', true), '')::uuid"
CLAIM = f"""
CREATE FUNCTION public.push_token_claim(p_token text, p_platform text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE actor uuid := {TENANT};
BEGIN
  IF actor IS NULL THEN RAISE EXCEPTION 'no_tenant'; END IF;
  INSERT INTO public.push_tokens (token, user_id, platform)
  VALUES (p_token, actor, p_platform)
  ON CONFLICT (token) DO UPDATE
  SET user_id = actor, platform = p_platform, last_seen_at = pg_catalog.now();
END $$"""


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("data", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("read_at", TSTZ),
    )
    op.create_index("notifications_user_created_idx", "notifications", ["user_id", "created_at"])
    op.create_table(
        "push_tokens",
        sa.Column("token", sa.Text, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.Text, nullable=False),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("last_seen_at", TSTZ, nullable=False, server_default=NOW),
    )
    op.create_index("push_tokens_user_idx", "push_tokens", ["user_id"])
    for table in ("notifications", "push_tokens"):
        op.execute(f"REVOKE ALL ON {table} FROM app_legacy")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (user_id = {TENANT}) WITH CHECK (user_id = {TENANT})"
        )
    # FORCE RLS applies to the definer (app_owner) too. Only that role can use this policy.
    op.execute(
        "CREATE POLICY owner_claim ON push_tokens TO app_owner USING (true) WITH CHECK (true)"
    )
    op.execute(CLAIM)
    op.execute("REVOKE ALL ON FUNCTION public.push_token_claim(text, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION public.push_token_claim(text, text) TO app_rw")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.push_token_claim(text, text)")
    op.drop_table("push_tokens")
    op.drop_table("notifications")
