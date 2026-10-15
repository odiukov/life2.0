"""Chat tasks, the transcript, pending actions, checkpoints under RLS, per-user telemetry consent.

Revision ID: c0010_chat
Revises: c0009_auth_functions
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c0010_chat"
down_revision: str | Sequence[str] | None = "c0009_auth_functions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT = "NULLIF(current_setting('app.user_id', true), '')::uuid"
THREAD_OWNER = "split_part(thread_id, ':', 1) = NULLIF(current_setting('app.user_id', true), '')"
AGENTS = "('sleep', 'workout', 'nutrition', 'body', 'mood', 'habits', 'recovery', 'medication', 'kitchen', 'finance', 'calendar', 'home')"
# The SQL of langgraph-checkpoint-postgres 3.1.3 MIGRATIONS[1..4, 9], copied so this revision never
# changes with the library. Indexes are created without CONCURRENTLY inside the migration transaction.
CHECKPOINT_DDL = [
    "DROP TABLE IF EXISTS checkpoint_writes, checkpoint_blobs, checkpoints, checkpoint_migrations",
    "CREATE TABLE checkpoint_migrations (v INTEGER PRIMARY KEY)",
    """CREATE TABLE checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id))""",
    """CREATE TABLE checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version))""",
    """CREATE TABLE checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    task_path TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx))""",
    "CREATE INDEX checkpoints_thread_id_idx ON checkpoints(thread_id)",
    "CREATE INDEX checkpoint_blobs_thread_id_idx ON checkpoint_blobs(thread_id)",
    "CREATE INDEX checkpoint_writes_thread_id_idx ON checkpoint_writes(thread_id)",
    "INSERT INTO checkpoint_migrations (v) SELECT generate_series(0, 9)",
]


def _if_legacy(sql: str) -> str:
    """Skip grants for the retired role on fresh installations."""
    return f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_legacy') THEN {sql}; END IF; END $$"


def upgrade() -> None:
    # Existing checkpoints (written by the legacy orchestrator) have no owner and are dropped.
    for statement in CHECKPOINT_DDL:
        op.execute(statement)
    for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY thread_owner ON {table} USING ({THREAD_OWNER}) WITH CHECK ({THREAD_OWNER})"
        )
    op.execute("REVOKE INSERT, UPDATE, DELETE ON checkpoint_migrations FROM app_rw")

    op.execute(
        f"""CREATE TABLE chat_tasks (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        household_id uuid REFERENCES households(id) ON DELETE SET NULL,
        lead_agent text CONSTRAINT chat_tasks_lead_agent_check CHECK (lead_agent IN {AGENTS}),
        title text CONSTRAINT chat_tasks_title_check CHECK (char_length(title) <= 120),
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now())"""
    )
    op.execute("CREATE INDEX chat_tasks_user_updated_idx ON chat_tasks (user_id, updated_at DESC)")
    op.execute(
        """CREATE TABLE chat_messages (
        task_id uuid NOT NULL REFERENCES chat_tasks(id) ON DELETE CASCADE,
        seq integer NOT NULL,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role text NOT NULL CONSTRAINT chat_messages_role_check CHECK (role IN ('user', 'assistant')),
        text text NOT NULL DEFAULT '',
        agent text,
        consulted text[] NOT NULL DEFAULT '{}'::text[],
        attachments jsonb NOT NULL DEFAULT '[]'::jsonb,
        action jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT chat_messages_pkey PRIMARY KEY (task_id, seq))"""
    )
    op.execute(
        """CREATE TABLE pending_actions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        household_id uuid REFERENCES households(id) ON DELETE SET NULL,
        task_id uuid NOT NULL REFERENCES chat_tasks(id) ON DELETE CASCADE,
        agent text NOT NULL CONSTRAINT pending_actions_agent_check CHECK (agent IN ('calendar', 'home')),
        kind text NOT NULL,
        payload jsonb NOT NULL,
        summary text NOT NULL,
        status text NOT NULL DEFAULT 'pending' CONSTRAINT pending_actions_status_check
          CHECK (status IN ('pending', 'applying', 'applied', 'rejected', 'expired', 'failed')),
        result_code text,
        created_at timestamptz NOT NULL DEFAULT now(),
        expires_at timestamptz NOT NULL,
        decided_at timestamptz)"""
    )
    op.execute(
        "CREATE UNIQUE INDEX pending_actions_one_pending_per_task ON pending_actions (task_id) WHERE status = 'pending'"
    )
    for table in ("chat_tasks", "chat_messages", "pending_actions"):
        op.execute(_if_legacy(f"REVOKE ALL ON {table} FROM app_legacy"))
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        check = f"user_id = {TENANT}"
        if table != "chat_tasks":
            check += f" AND EXISTS (SELECT 1 FROM chat_tasks t WHERE t.id = {table}.task_id AND t.user_id = {table}.user_id)"
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table} USING (user_id = {TENANT}) WITH CHECK ({check})"
        )

    # telemetry_consent: the literal 'owner' row goes; consent is per user from now on.
    op.execute("ALTER TABLE telemetry_consent NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY tenant_isolation ON telemetry_consent")
    # Normalize valid UUID spellings and combine duplicates conservatively: a denial wins.
    op.execute("DELETE FROM telemetry_consent WHERE NOT pg_input_is_valid(user_id, 'uuid')")
    op.execute(
        "CREATE TEMP TABLE consent_normalized ON COMMIT DROP AS "
        "SELECT user_id::uuid AS user_id, bool_and(bodies_ok) AS bodies_ok, "
        "max(updated_at) AS updated_at FROM telemetry_consent GROUP BY user_id::uuid"
    )
    op.execute("DELETE FROM telemetry_consent")
    op.execute("ALTER TABLE telemetry_consent ALTER COLUMN user_id TYPE uuid USING user_id::uuid")
    op.execute("ALTER TABLE users NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "INSERT INTO telemetry_consent (user_id, bodies_ok, updated_at) "
        "SELECT c.user_id, c.bodies_ok, c.updated_at FROM consent_normalized c "
        "JOIN users u ON u.id = c.user_id"
    )
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        "ALTER TABLE telemetry_consent ADD CONSTRAINT telemetry_consent_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE"
    )
    op.execute(
        f"CREATE POLICY tenant_isolation ON telemetry_consent USING (user_id = {TENANT}) WITH CHECK (user_id = {TENANT})"
    )
    op.execute("ALTER TABLE telemetry_consent FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE telemetry_consent NO FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY tenant_isolation ON telemetry_consent")
    op.execute("ALTER TABLE telemetry_consent DROP CONSTRAINT telemetry_consent_user_id_fkey")
    op.execute("ALTER TABLE telemetry_consent ALTER COLUMN user_id TYPE text USING user_id::text")
    op.execute(
        "CREATE POLICY tenant_isolation ON telemetry_consent "
        "USING (user_id = NULLIF(current_setting('app.user_id', true), '')) "
        "WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), ''))"
    )
    op.execute(
        "INSERT INTO telemetry_consent (user_id, bodies_ok) VALUES ('owner', true) ON CONFLICT (user_id) DO NOTHING"
    )
    op.execute("ALTER TABLE telemetry_consent FORCE ROW LEVEL SECURITY")
    op.execute("DROP TABLE pending_actions, chat_messages, chat_tasks")
    op.execute("DROP TABLE checkpoint_writes, checkpoint_blobs, checkpoints, checkpoint_migrations")
