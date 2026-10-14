"""Every table in the application database. Alembic revisions must keep the DB equal to this."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID

from shared.schema.metadata import metadata

NOW = text("now()")
NEW_UUID = text("gen_random_uuid()")
TSTZ = TIMESTAMP(timezone=True)


def _user_fk() -> Column[Any]:
    return Column(
        "user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


users = Table(
    "users",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    Column("name", Text, nullable=False),
    Column("timezone", Text, nullable=False, server_default=text("'UTC'")),
    Column("preferences", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
)

health_logs = Table(
    "health_logs",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _user_fk(),
    Column("agent", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("data", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("recorded_at", TSTZ, nullable=False, server_default=NOW),
    Column("source", Text, nullable=False, server_default=text("'manual'")),
)
Index(
    "health_logs_user_id_recorded_at_idx", health_logs.c.user_id, health_logs.c.recorded_at.desc()
)
Index(
    "health_logs_user_source_type_recorded_uniq",
    health_logs.c.user_id,
    health_logs.c.source,
    health_logs.c.type,
    health_logs.c.recorded_at,
    unique=True,
)

tasks = Table(
    "tasks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    Column("task_id", UUID(as_uuid=True), nullable=False, unique=True, server_default=NEW_UUID),
    Column("context_id", UUID(as_uuid=True)),
    Column("agent", Text, nullable=False),
    Column("skill_id", Text),
    Column("state", Text, nullable=False, server_default=text("'submitted'")),
    Column("input", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("output", Text),
    Column("artifacts", JSONB),
    Column("history", JSONB),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("updated_at", TSTZ, nullable=False, server_default=NOW),
)
Index("tasks_state_idx", tasks.c.agent, tasks.c.state, tasks.c.updated_at.desc())

habits = Table(
    "habits",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _user_fk(),
    Column("name", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("cadence_type", Text, nullable=False),
    Column("cadence_days", ARRAY(Text)),
    Column("target_value", Numeric),
    Column("unit", Text),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("archived_at", TSTZ),
    CheckConstraint("kind IN ('boolean', 'quantitative')", name="habits_kind_check"),
    CheckConstraint("cadence_type IN ('daily', 'weekly')", name="habits_cadence_type_check"),
)
Index(
    "habits_user_name_active_uniq",
    habits.c.user_id,
    habits.c.name,
    unique=True,
    postgresql_where=habits.c.archived_at.is_(None),
)
Index("habits_active_idx", habits.c.archived_at, postgresql_where=habits.c.archived_at.is_(None))
Index("habits_user_id_idx", habits.c.user_id)

medications = Table(
    "medications",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _user_fk(),
    Column("name", Text, nullable=False),
    Column("dose", Text),
    Column("schedule", Text, nullable=False),
    Column("notes", Text),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("active_until", TSTZ),
    Column("archived_at", TSTZ),
)
Index(
    "medications_user_name_active_uniq",
    medications.c.user_id,
    medications.c.name,
    unique=True,
    postgresql_where=medications.c.archived_at.is_(None),
)
Index(
    "medications_active_idx",
    medications.c.archived_at,
    postgresql_where=medications.c.archived_at.is_(None),
)
Index("medications_user_id_idx", medications.c.user_id)

finance_transactions = Table(
    "finance_transactions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _user_fk(),
    Column("txn_id", Text, nullable=False),
    Column("ts", TSTZ, nullable=False),
    Column("direction", Text, nullable=False),
    Column("amount", Numeric(14, 2), nullable=False),
    Column("currency", Text, nullable=False),
    Column("description", Text),
    Column("category", Text),
    Column("source", Text, nullable=False, server_default=text("'payoneer_csv'")),
    Column("raw", JSONB),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    CheckConstraint("direction IN ('IN', 'OUT')", name="finance_transactions_direction_check"),
    UniqueConstraint("user_id", "txn_id", name="finance_transactions_user_txn_uniq"),
)
Index("finance_transactions_ts_idx", finance_transactions.c.ts)
Index(
    "finance_transactions_category_ts_idx",
    finance_transactions.c.category,
    finance_transactions.c.ts,
    postgresql_where=finance_transactions.c.category.is_not(None),
)
Index(
    "finance_transactions_user_id_ts_idx",
    finance_transactions.c.user_id,
    finance_transactions.c.ts.desc(),
)

finance_category_cache = Table(
    "finance_category_cache",
    metadata,
    _user_fk(),
    Column("desc_key", Text, nullable=False),
    Column("category", Text, nullable=False),
    Column("updated_at", TSTZ, nullable=False, server_default=NOW),
    PrimaryKeyConstraint("user_id", "desc_key", name="finance_category_cache_pkey"),
)

telemetry_consent = Table(
    "telemetry_consent",
    metadata,
    Column("user_id", Text, primary_key=True),
    Column("bodies_ok", Boolean, nullable=False, server_default=text("false")),
    Column("updated_at", TSTZ, nullable=False, server_default=NOW),
)

integrations_credentials = Table(
    "integrations_credentials",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _user_fk(),
    Column("service", Text, nullable=False),
    Column("secret_id", UUID(as_uuid=True)),
    Column("payload_dev", JSONB),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("last_used_at", TSTZ),
    UniqueConstraint("user_id", "service", name="integrations_credentials_user_id_service_key"),
    CheckConstraint(
        "service IN ('ha', 'yazio', 'google_calendar', 'garmin')",
        name="integrations_credentials_service_check",
    ),
    CheckConstraint(
        "(secret_id IS NOT NULL)::int + (payload_dev IS NOT NULL)::int = 1",
        name="integrations_credentials_one_backend_check",
    ),
)
Index("integrations_credentials_user_idx", integrations_credentials.c.user_id)

oauth_state = Table(
    "oauth_state",
    metadata,
    Column("nonce", UUID(as_uuid=True), primary_key=True),
    _user_fk(),
    Column("service", Text, nullable=False),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("used_at", TSTZ),
    Column("code_verifier", Text),
    CheckConstraint("service IN ('google_calendar')", name="oauth_state_service_check"),
)
Index("oauth_state_user_idx", oauth_state.c.user_id)

# Tables whose rows belong to one user. `users` itself is isolated by `id`.
RLS_TABLES: tuple[str, ...] = (
    "health_logs",
    "habits",
    "medications",
    "finance_transactions",
    "finance_category_cache",
    "integrations_credentials",
    "oauth_state",
    "telemetry_consent",
)
