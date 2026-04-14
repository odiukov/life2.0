CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    preferences JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS health_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent TEXT NOT NULL,
    type TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    context_id UUID,
    agent TEXT NOT NULL,
    skill_id TEXT,
    state TEXT NOT NULL DEFAULT 'submitted',
    input JSONB NOT NULL DEFAULT '{}',
    output TEXT,
    artifacts JSONB,
    history JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS tasks_task_id_idx ON tasks (task_id);
CREATE INDEX IF NOT EXISTS tasks_state_idx ON tasks (agent, state, updated_at DESC);

-- Default user (single-user system for now)
INSERT INTO users (name, timezone) VALUES ('me', 'Europe/Kyiv')
ON CONFLICT DO NOTHING;

CREATE UNIQUE INDEX IF NOT EXISTS health_logs_dedup_idx
  ON health_logs (source, type, recorded_at);
