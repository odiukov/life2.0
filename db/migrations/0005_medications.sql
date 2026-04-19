-- 0005: Medications config table. Event log lives in health_logs with type='medication_taken'.
BEGIN;

CREATE TABLE IF NOT EXISTS medications (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    dose          TEXT,                            -- free-text e.g. "200mg", "2 tabs"
    schedule      TEXT NOT NULL,                   -- RRULE-ish free-text: "daily 21:00", "mon,wed,fri morning"
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    active_until  TIMESTAMPTZ,                     -- NULL = open-ended; set on /med stop
    archived_at   TIMESTAMPTZ                      -- soft-delete
);

CREATE UNIQUE INDEX IF NOT EXISTS medications_name_active_uniq
    ON medications (name) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS medications_active_idx
    ON medications (archived_at) WHERE archived_at IS NULL;

COMMIT;
