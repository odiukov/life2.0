"""Every table in the application database. Alembic revisions must keep the DB equal to this."""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    Time,
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

auth_identities = Table(
    "auth_identities",
    metadata,
    Column("provider", Text, primary_key=True),
    Column("subject", Text, primary_key=True),
    _user_fk(),
    Column("email", Text),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    UniqueConstraint("user_id", "provider", name="auth_identities_user_provider_key"),
)

auth_flows = Table(
    "auth_flows",
    metadata,
    Column("state_hash", Text, primary_key=True),
    Column("provider", Text, nullable=False),
    Column("code_verifier", Text, nullable=False),
    Column("nonce", Text, nullable=False),
    Column("app_challenge", Text, nullable=False),
    Column("expires_at", TSTZ, nullable=False),
)

auth_tickets = Table(
    "auth_tickets",
    metadata,
    Column("ticket_hash", Text, primary_key=True),
    _user_fk(),
    Column("app_challenge", Text, nullable=False),
    Column("expires_at", TSTZ, nullable=False),
)

auth_sessions = Table(
    "auth_sessions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    _user_fk(),
    Column("refresh_hash", Text, nullable=False),
    Column("expires_at", TSTZ, nullable=False),
    Column("revoked_at", TSTZ),
)
Index("auth_sessions_user_idx", auth_sessions.c.user_id)

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
    Column(
        "user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    ),
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
    Column("payload_enc", LargeBinary),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("last_used_at", TSTZ),
    UniqueConstraint("user_id", "service", name="integrations_credentials_user_id_service_key"),
    CheckConstraint(
        "service IN ('yazio', 'google_calendar', 'garmin')",
        name="integrations_credentials_service_check",
    ),
    CheckConstraint(
        "(secret_id IS NOT NULL)::int + (payload_dev IS NOT NULL)::int + (payload_enc IS NOT NULL)::int = 1",
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
    "integration_sync_state",
    "oauth_state",
    "telemetry_consent",
    "notifications",
    "push_tokens",
    "chat_tasks",
    "chat_messages",
    "pending_actions",
)

notifications = Table(
    "notifications",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _user_fk(),
    Column("kind", Text, nullable=False),
    Column("title", Text, nullable=False),
    Column("body", Text, nullable=False),
    Column("data", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("read_at", TSTZ),
)
Index("notifications_user_created_idx", notifications.c.user_id, notifications.c.created_at)

push_tokens = Table(
    "push_tokens",
    metadata,
    Column("token", Text, primary_key=True),
    _user_fk(),
    Column("platform", Text, nullable=False),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("last_seen_at", TSTZ, nullable=False, server_default=NOW),
)
Index("push_tokens_user_idx", push_tokens.c.user_id)

CURRENT_HOUSEHOLD = text("current_household_id()")


def _household_fk() -> Column[Any]:
    return Column(
        "household_id",
        UUID(as_uuid=True),
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
        server_default=CURRENT_HOUSEHOLD,
    )


households = Table(
    "households",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    Column("name", Text, nullable=False),
    Column("timezone", Text, nullable=False, server_default=text("'UTC'")),
    Column("digest_time", Time, nullable=False, server_default=text("'18:00'")),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
)

household_members = Table(
    "household_members",
    metadata,
    Column(
        "household_id",
        UUID(as_uuid=True),
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    ),
    _user_fk(),
    Column("role", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("joined_at", TSTZ, nullable=False, server_default=NOW),
    PrimaryKeyConstraint("household_id", "user_id", name="household_members_pkey"),
    UniqueConstraint("user_id", name="household_members_user_id_key"),
    CheckConstraint("role IN ('owner', 'member')", name="household_members_role_check"),
)
Index(
    "household_members_one_owner",
    household_members.c.household_id,
    unique=True,
    postgresql_where=text("role = 'owner'"),
)

household_invites = Table(
    "household_invites",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _household_fk(),
    Column("code_hash", LargeBinary, nullable=False),
    Column(
        "created_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    ),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("expires_at", TSTZ, nullable=False),
    Column("redeemed_at", TSTZ),
    Column("redeemed_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")),
    UniqueConstraint("code_hash", name="household_invites_code_hash_key"),
)

household_join_attempts = Table(
    "household_join_attempts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _user_fk(),
    Column("attempted_at", TSTZ, nullable=False, server_default=NOW),
    Column("succeeded", Boolean, nullable=False),
)
Index(
    "household_join_attempts_user_idx",
    household_join_attempts.c.user_id,
    household_join_attempts.c.attempted_at,
)

household_tables = Table(
    "household_tables",
    metadata,
    Column("table_name", Text, primary_key=True),
    Column("move_on_join", Boolean, nullable=False),
    Column("item_filter", Text),
)

kitchen_batches = Table(
    "kitchen_batches",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _household_fk(),
    Column("name", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("category", Text, nullable=False),
    Column("quantity", Numeric(14, 3), nullable=False),
    Column("unit", Text, nullable=False),
    Column("location", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("opened", Boolean, nullable=False, server_default=text("false")),
    Column("opened_on", Date),
    Column("added_at", TSTZ, nullable=False),
    Column("added_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")),
    Column("expires_on", Date, nullable=False),
    Column("expiry_source", Text, nullable=False),
    Column("next_check_on", Date, nullable=False),
    Column("source", Text, nullable=False),
    Column("last_group_id", UUID(as_uuid=True)),
    CheckConstraint("quantity >= 0", name="kitchen_batches_quantity_check"),
    CheckConstraint("unit IN ('pcs', 'g', 'ml', 'pack')", name="kitchen_batches_unit_check"),
    CheckConstraint(
        "location IN ('fridge', 'freezer', 'pantry')", name="kitchen_batches_location_check"
    ),
    CheckConstraint(
        "status IN ('active', 'consumed', 'discarded')", name="kitchen_batches_status_check"
    ),
)
Index(
    "kitchen_batches_expiry_idx",
    kitchen_batches.c.household_id,
    kitchen_batches.c.status,
    kitchen_batches.c.expires_on,
)
Index(
    "kitchen_batches_name_idx",
    kitchen_batches.c.household_id,
    kitchen_batches.c.status,
    kitchen_batches.c.name,
)

kitchen_operation_groups = Table(
    "kitchen_operation_groups",
    metadata,
    Column("insertion_order", BigInteger, Identity(always=True), nullable=False),
    Column("id", UUID(as_uuid=True), primary_key=True),
    _household_fk(),
    _user_fk(),
    Column("created_at", TSTZ, nullable=False),
    Column("source", Text, nullable=False),
    Column("changes", JSONB, nullable=False),
    Column("undone_at", TSTZ),
    Column("undone_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")),
)
Index(
    "kitchen_operation_groups_user_idx",
    kitchen_operation_groups.c.household_id,
    kitchen_operation_groups.c.user_id,
    kitchen_operation_groups.c.created_at,
)

kitchen_clarifications = Table(
    "kitchen_clarifications",
    metadata,
    _household_fk(),
    _user_fk(),
    Column("payload", JSONB, nullable=False),
    Column("expires_at", TSTZ, nullable=False),
    PrimaryKeyConstraint("household_id", "user_id", name="kitchen_clarifications_pkey"),
)

kitchen_digest_runs = Table(
    "kitchen_digest_runs",
    metadata,
    _household_fk(),
    Column("local_date", Date, nullable=False),
    Column("sent_at", TSTZ, nullable=False, server_default=NOW),
    PrimaryKeyConstraint("household_id", "local_date", name="kitchen_digest_runs_pkey"),
)

# Registry completeness and move behavior are checked against the migrated database.
HOUSEHOLD_TABLES: dict[str, bool] = {
    "household_credentials": False,
    "household_invites": False,
    "kitchen_batches": True,
    "kitchen_operation_groups": True,
    "kitchen_clarifications": False,
    "kitchen_digest_runs": False,
}


integration_sync_state = Table(
    "integration_sync_state",
    metadata,
    _user_fk(),
    Column("service", Text, nullable=False),
    Column("last_attempt_at", TSTZ),
    Column("last_success_at", TSTZ),
    Column("last_error", Text),
    PrimaryKeyConstraint("user_id", "service", name="integration_sync_state_pkey"),
    CheckConstraint("service IN ('garmin', 'yazio')", name="integration_sync_state_service_check"),
)


household_credentials = Table(
    "household_credentials",
    metadata,
    Column(
        "household_id",
        UUID(as_uuid=True),
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("service", Text, nullable=False),
    Column("payload_enc", LargeBinary, nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column("updated_by", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")),
    Column("updated_at", TSTZ, nullable=False, server_default=NOW),
    PrimaryKeyConstraint("household_id", "service", name="household_credentials_pkey"),
    CheckConstraint("service IN ('ha')", name="household_credentials_service_check"),
)


CHAT_AGENTS = (
    "sleep",
    "workout",
    "nutrition",
    "body",
    "mood",
    "habits",
    "recovery",
    "medication",
    "kitchen",
    "finance",
    "calendar",
    "home",
)

chat_tasks = Table(
    "chat_tasks",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _user_fk(),
    Column("household_id", UUID(as_uuid=True), ForeignKey("households.id", ondelete="SET NULL")),
    Column("lead_agent", Text),
    Column("title", Text),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("updated_at", TSTZ, nullable=False, server_default=NOW),
    CheckConstraint(
        f"lead_agent IN ({', '.join(repr(a) for a in CHAT_AGENTS)})",
        name="chat_tasks_lead_agent_check",
    ),
    CheckConstraint("char_length(title) <= 120", name="chat_tasks_title_check"),
)
Index("chat_tasks_user_updated_idx", chat_tasks.c.user_id, chat_tasks.c.updated_at.desc())

chat_messages = Table(
    "chat_messages",
    metadata,
    Column(
        "task_id",
        UUID(as_uuid=True),
        ForeignKey("chat_tasks.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("seq", Integer, nullable=False),
    _user_fk(),
    Column("role", Text, nullable=False),
    Column("text", Text, nullable=False, server_default=text("''")),
    Column("agent", Text),
    Column("consulted", ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")),
    Column("attachments", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("action", JSONB),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    PrimaryKeyConstraint("task_id", "seq", name="chat_messages_pkey"),
    CheckConstraint("role IN ('user', 'assistant')", name="chat_messages_role_check"),
)

pending_actions = Table(
    "pending_actions",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=NEW_UUID),
    _user_fk(),
    Column("household_id", UUID(as_uuid=True), ForeignKey("households.id", ondelete="SET NULL")),
    Column(
        "task_id",
        UUID(as_uuid=True),
        ForeignKey("chat_tasks.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("agent", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("summary", Text, nullable=False),
    Column("status", Text, nullable=False, server_default=text("'pending'")),
    Column("result_code", Text),
    Column("created_at", TSTZ, nullable=False, server_default=NOW),
    Column("expires_at", TSTZ, nullable=False),
    Column("decided_at", TSTZ),
    CheckConstraint("agent IN ('calendar', 'home')", name="pending_actions_agent_check"),
    CheckConstraint(
        "status IN ('pending', 'applying', 'applied', 'rejected', 'expired', 'failed')",
        name="pending_actions_status_check",
    ),
)
Index(
    "pending_actions_one_pending_per_task",
    pending_actions.c.task_id,
    unique=True,
    postgresql_where=text("status = 'pending'"),
)

# LangGraph's AsyncPostgresSaver schema (langgraph-checkpoint-postgres 3.1.3, migrations 0–9).
CHECKPOINT_SCHEMA_VERSION = 9
checkpoint_migrations = Table(
    "checkpoint_migrations", metadata, Column("v", Integer, primary_key=True)
)
checkpoints = Table(
    "checkpoints",
    metadata,
    Column("thread_id", Text, nullable=False),
    Column("checkpoint_ns", Text, nullable=False, server_default=text("''")),
    Column("checkpoint_id", Text, nullable=False),
    Column("parent_checkpoint_id", Text),
    Column("type", Text),
    Column("checkpoint", JSONB, nullable=False),
    Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    PrimaryKeyConstraint("thread_id", "checkpoint_ns", "checkpoint_id", name="checkpoints_pkey"),
)
Index("checkpoints_thread_id_idx", checkpoints.c.thread_id)
checkpoint_blobs = Table(
    "checkpoint_blobs",
    metadata,
    Column("thread_id", Text, nullable=False),
    Column("checkpoint_ns", Text, nullable=False, server_default=text("''")),
    Column("channel", Text, nullable=False),
    Column("version", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("blob", LargeBinary),
    PrimaryKeyConstraint(
        "thread_id", "checkpoint_ns", "channel", "version", name="checkpoint_blobs_pkey"
    ),
)
Index("checkpoint_blobs_thread_id_idx", checkpoint_blobs.c.thread_id)
checkpoint_writes = Table(
    "checkpoint_writes",
    metadata,
    Column("thread_id", Text, nullable=False),
    Column("checkpoint_ns", Text, nullable=False, server_default=text("''")),
    Column("checkpoint_id", Text, nullable=False),
    Column("task_id", Text, nullable=False),
    Column("idx", Integer, nullable=False),
    Column("channel", Text, nullable=False),
    Column("type", Text),
    Column("blob", LargeBinary, nullable=False),
    Column("task_path", Text, nullable=False, server_default=text("''")),
    PrimaryKeyConstraint(
        "thread_id",
        "checkpoint_ns",
        "checkpoint_id",
        "task_id",
        "idx",
        name="checkpoint_writes_pkey",
    ),
)
Index("checkpoint_writes_thread_id_idx", checkpoint_writes.c.thread_id)
