-- 0004: Alert emission throttling. One row per rule_id with last-emitted timestamp.
BEGIN;

CREATE TABLE IF NOT EXISTS alert_emissions (
    rule_id       TEXT PRIMARY KEY,
    last_emitted  TIMESTAMPTZ NOT NULL
);

COMMIT;
