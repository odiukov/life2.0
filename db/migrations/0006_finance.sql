-- 0006: Payoneer finance transactions + description→category cache.
BEGIN;

CREATE TABLE IF NOT EXISTS finance_transactions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    txn_id      TEXT NOT NULL UNIQUE,                           -- Payoneer Transaction ID = natural dedup key
    ts          TIMESTAMPTZ NOT NULL,
    direction   TEXT NOT NULL CHECK (direction IN ('IN','OUT')),
    amount      NUMERIC(14,2) NOT NULL,                         -- always stored positive
    currency    TEXT NOT NULL,
    description TEXT,
    category    TEXT,                                           -- NULL until categorize_new() fills it
    source      TEXT NOT NULL DEFAULT 'payoneer_csv',
    raw         JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS finance_transactions_ts_idx
    ON finance_transactions (ts);

CREATE INDEX IF NOT EXISTS finance_transactions_category_ts_idx
    ON finance_transactions (category, ts)
    WHERE category IS NOT NULL;

CREATE TABLE IF NOT EXISTS finance_category_cache (
    desc_key    TEXT PRIMARY KEY,                               -- normalized description (lower/trim/stripped dates+nums)
    category    TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
