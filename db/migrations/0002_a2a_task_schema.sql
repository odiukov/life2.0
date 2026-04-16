-- 0002: Extend tasks table for A2A v0.2 Task objects.
BEGIN;

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS task_id UUID UNIQUE,
    ADD COLUMN IF NOT EXISTS context_id UUID,
    ADD COLUMN IF NOT EXISTS state TEXT NOT NULL DEFAULT 'submitted',
    ADD COLUMN IF NOT EXISTS skill_id TEXT,
    ADD COLUMN IF NOT EXISTS artifacts JSONB,
    ADD COLUMN IF NOT EXISTS history JSONB,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Backfill skill_id from legacy task_type column (only if that column still exists)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'tasks' AND column_name = 'task_type'
    ) THEN
        UPDATE tasks SET skill_id = task_type WHERE skill_id IS NULL;
    END IF;
END $$;

-- Backfill task_id (generate fresh UUIDs for pre-existing rows)
UPDATE tasks SET task_id = gen_random_uuid() WHERE task_id IS NULL;

-- Make task_id required going forward
ALTER TABLE tasks ALTER COLUMN task_id SET NOT NULL;

-- Drop legacy column (skill_id replaces it)
ALTER TABLE tasks DROP COLUMN IF EXISTS task_type;

-- UNIQUE on task_id already creates a btree index; no separate tasks_task_id_idx needed.
CREATE INDEX IF NOT EXISTS tasks_state_idx ON tasks (agent, state, updated_at DESC);

COMMIT;
