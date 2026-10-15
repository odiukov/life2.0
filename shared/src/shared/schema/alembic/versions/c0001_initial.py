"""Initial schema, grants and row-level security.

Revision ID: c0001_initial
Revises:
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "c0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = ("core",)
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")
NEW_UUID = sa.text("gen_random_uuid()")
TSTZ = pg.TIMESTAMP(timezone=True)
UUID = pg.UUID(as_uuid=True)
EMPTY_JSON = sa.text("'{}'::jsonb")
TENANT = "NULLIF(current_setting('app.user_id', true), '')::uuid"
RLS_TABLES = (
    "health_logs",
    "habits",
    "medications",
    "finance_transactions",
    "finance_category_cache",
    "integrations_credentials",
    "oauth_state",
    "telemetry_consent",
)


def _user_fk() -> sa.Column:
    return sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _if_legacy(sql: str) -> str:
    """Skip grants for the retired role on fresh installations."""
    return f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_legacy') THEN {sql}; END IF; END $$"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("timezone", sa.Text, nullable=False, server_default=sa.text("'UTC'")),
        sa.Column("preferences", pg.JSONB, nullable=False, server_default=EMPTY_JSON),
    )
    op.create_table(
        "health_logs",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        _user_fk(),
        sa.Column("agent", sa.Text, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("data", pg.JSONB, nullable=False, server_default=EMPTY_JSON),
        sa.Column("recorded_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("source", sa.Text, nullable=False, server_default=sa.text("'manual'")),
    )
    op.create_index(
        "health_logs_user_id_recorded_at_idx",
        "health_logs",
        ["user_id", sa.text("recorded_at DESC")],
    )
    op.create_index(
        "health_logs_user_source_type_recorded_uniq",
        "health_logs",
        ["user_id", "source", "type", "recorded_at"],
        unique=True,
    )
    op.create_table(
        "tasks",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        sa.Column("task_id", UUID, nullable=False, unique=True, server_default=NEW_UUID),
        sa.Column("context_id", UUID),
        sa.Column("agent", sa.Text, nullable=False),
        sa.Column("skill_id", sa.Text),
        sa.Column("state", sa.Text, nullable=False, server_default=sa.text("'submitted'")),
        sa.Column("input", pg.JSONB, nullable=False, server_default=EMPTY_JSON),
        sa.Column("output", sa.Text),
        sa.Column("artifacts", pg.JSONB),
        sa.Column("history", pg.JSONB),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("updated_at", TSTZ, nullable=False, server_default=NOW),
    )
    op.create_index("tasks_state_idx", "tasks", ["agent", "state", sa.text("updated_at DESC")])
    op.create_table(
        "habits",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        _user_fk(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("cadence_type", sa.Text, nullable=False),
        sa.Column("cadence_days", pg.ARRAY(sa.Text)),
        sa.Column("target_value", sa.Numeric),
        sa.Column("unit", sa.Text),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("archived_at", TSTZ),
        sa.CheckConstraint("kind IN ('boolean', 'quantitative')", name="habits_kind_check"),
        sa.CheckConstraint("cadence_type IN ('daily', 'weekly')", name="habits_cadence_type_check"),
    )
    op.create_index(
        "habits_user_name_active_uniq",
        "habits",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "habits_active_idx",
        "habits",
        ["archived_at"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index("habits_user_id_idx", "habits", ["user_id"])
    op.create_table(
        "medications",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        _user_fk(),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("dose", sa.Text),
        sa.Column("schedule", sa.Text, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("active_until", TSTZ),
        sa.Column("archived_at", TSTZ),
    )
    op.create_index(
        "medications_user_name_active_uniq",
        "medications",
        ["user_id", "name"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index(
        "medications_active_idx",
        "medications",
        ["archived_at"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    op.create_index("medications_user_id_idx", "medications", ["user_id"])
    op.create_table(
        "finance_transactions",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        _user_fk(),
        sa.Column("txn_id", sa.Text, nullable=False),
        sa.Column("ts", TSTZ, nullable=False),
        sa.Column("direction", sa.Text, nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("category", sa.Text),
        sa.Column("source", sa.Text, nullable=False, server_default=sa.text("'payoneer_csv'")),
        sa.Column("raw", pg.JSONB),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.CheckConstraint(
            "direction IN ('IN', 'OUT')", name="finance_transactions_direction_check"
        ),
        sa.UniqueConstraint("user_id", "txn_id", name="finance_transactions_user_txn_uniq"),
    )
    op.create_index("finance_transactions_ts_idx", "finance_transactions", ["ts"])
    op.create_index(
        "finance_transactions_category_ts_idx",
        "finance_transactions",
        ["category", "ts"],
        postgresql_where=sa.text("category IS NOT NULL"),
    )
    op.create_index(
        "finance_transactions_user_id_ts_idx",
        "finance_transactions",
        ["user_id", sa.text("ts DESC")],
    )
    op.create_table(
        "finance_category_cache",
        _user_fk(),
        sa.Column("desc_key", sa.Text, nullable=False),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("updated_at", TSTZ, nullable=False, server_default=NOW),
        sa.PrimaryKeyConstraint("user_id", "desc_key", name="finance_category_cache_pkey"),
    )
    op.create_table(
        "telemetry_consent",
        sa.Column("user_id", sa.Text, primary_key=True),
        sa.Column("bodies_ok", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", TSTZ, nullable=False, server_default=NOW),
    )
    op.create_table(
        "integrations_credentials",
        sa.Column("id", UUID, primary_key=True, server_default=NEW_UUID),
        _user_fk(),
        sa.Column("service", sa.Text, nullable=False),
        sa.Column("secret_id", UUID),
        sa.Column("payload_dev", pg.JSONB),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("last_used_at", TSTZ),
        sa.UniqueConstraint(
            "user_id", "service", name="integrations_credentials_user_id_service_key"
        ),
        sa.CheckConstraint(
            "service IN ('ha', 'yazio', 'google_calendar', 'garmin')",
            name="integrations_credentials_service_check",
        ),
        sa.CheckConstraint(
            "(secret_id IS NOT NULL)::int + (payload_dev IS NOT NULL)::int = 1",
            name="integrations_credentials_one_backend_check",
        ),
    )
    op.create_index("integrations_credentials_user_idx", "integrations_credentials", ["user_id"])
    op.create_table(
        "oauth_state",
        sa.Column("nonce", UUID, primary_key=True),
        _user_fk(),
        sa.Column("service", sa.Text, nullable=False),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("used_at", TSTZ),
        sa.Column("code_verifier", sa.Text),
        sa.CheckConstraint("service IN ('google_calendar')", name="oauth_state_service_check"),
    )
    op.create_index("oauth_state_user_idx", "oauth_state", ["user_id"])
    op.execute(
        "CREATE OR REPLACE FUNCTION gc_oauth_state() RETURNS void LANGUAGE sql AS $$ "
        "DELETE FROM oauth_state WHERE created_at < now() - interval '1 hour'; $$"
    )
    op.execute(
        "INSERT INTO telemetry_consent (user_id, bodies_ok) VALUES ('owner', true) "
        "ON CONFLICT (user_id) DO NOTHING"
    )

    # Grants: DML only for the application roles; the owner keeps DDL.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_rw")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw"
    )

    # Alembic creates its control table before this revision. Its history is owner-only.
    op.execute("REVOKE ALL PRIVILEGES ON TABLE alembic_version FROM app_rw")

    # Row-level security, enforced even for the table owner.
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        tenant = (
            "NULLIF(current_setting('app.user_id', true), '')"
            if table == "telemetry_consent"
            else TENANT
        )
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} "
            f"USING (user_id = {tenant}) WITH CHECK (user_id = {tenant})"
        )
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON users USING (id = {TENANT}) WITH CHECK (id = {TENANT})"
    )

    op.execute(
        _if_legacy(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_legacy; "
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_legacy; "
            "REVOKE ALL PRIVILEGES ON TABLE alembic_version FROM app_legacy"
        )
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS gc_oauth_state()")
    for table in (
        "oauth_state",
        "integrations_credentials",
        "telemetry_consent",
        "finance_category_cache",
        "finance_transactions",
        "medications",
        "habits",
        "tasks",
        "health_logs",
        "users",
    ):
        op.drop_table(table)
