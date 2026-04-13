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
    agent TEXT NOT NULL,
    task_type TEXT NOT NULL,
    input JSONB NOT NULL DEFAULT '{}',
    output TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Default user (single-user system for now)
INSERT INTO users (name, timezone) VALUES ('me', 'Europe/Kyiv')
ON CONFLICT DO NOTHING;

CREATE UNIQUE INDEX IF NOT EXISTS health_logs_dedup_idx
  ON health_logs (source, type, recorded_at);
