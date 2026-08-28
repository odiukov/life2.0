-- 0003: Habits registry table.
BEGIN;

CREATE TABLE IF NOT EXISTS habits (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('boolean', 'quantitative')),
    cadence_type  TEXT NOT NULL CHECK (cadence_type IN ('daily', 'weekly')),
    cadence_days  TEXT[],
    target_value  NUMERIC,
    unit          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at   TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS habits_name_active_uniq
    ON habits (name) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS habits_active_idx
    ON habits (archived_at) WHERE archived_at IS NULL;

COMMIT;
