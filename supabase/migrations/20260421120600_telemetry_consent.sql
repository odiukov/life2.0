-- Per-user consent flag for body-capture in telemetry.
-- Default FALSE: bodies are redacted unless user has explicitly opted in.
CREATE TABLE IF NOT EXISTS telemetry_consent (
    user_id    TEXT PRIMARY KEY,
    bodies_ok  BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed: owner gets true for dev convenience. Revoke with
-- UPDATE telemetry_consent SET bodies_ok=false WHERE user_id='owner';
INSERT INTO telemetry_consent (user_id, bodies_ok)
VALUES ('owner', TRUE)
ON CONFLICT (user_id) DO NOTHING;
