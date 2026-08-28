-- Per-user tenancy key.
-- DEV NOTE: references public.users(id) locally. At Supabase cutover, a
-- follow-up migration will drop these FKs and re-add them against auth.users(id).

-- ---------------------------------------------------------------------------
-- CREATE stubs for tables that exist as health_logs type-values in the current
-- single-user stack but are expected as separate tables in the multi-user
-- design. These stubs are reconstructed from sync_service/app/mapper.py,
-- sync_service/app/apple_health.py, and query shapes in shared/shared/db.py
-- and orchestrator/app/db.py.
--
-- NOTE: All existing data for these types still lives in health_logs; these
-- tables will be populated by a future denormalisation migration (see Plan
-- Phase B). Creating them here lets the user_id FK + indexes be applied
-- consistently across all 9 per-user tables.
-- ---------------------------------------------------------------------------

-- sleep_session: reconstructed from mapper.map_sleep() → health_logs row shape.
-- Key columns for index: start_at (maps to recorded_at / start_time in data).
CREATE TABLE IF NOT EXISTS public.sleep_session (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    start_at         timestamptz NOT NULL,
    end_at           timestamptz,
    duration_seconds int,
    score            int,
    deep_sleep_seconds int,
    rem_sleep_seconds  int,
    light_sleep_seconds int,
    awake_seconds    int,
    hrv_weekly_avg   numeric,
    source           text        NOT NULL DEFAULT 'garmin',
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- daily_stats: reconstructed from mapper.map_daily_stats() → health_logs row shape.
-- Key columns for index: date.
CREATE TABLE IF NOT EXISTS public.daily_stats (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    date             date        NOT NULL,
    steps            int,
    calories_active  int,
    stress_avg       numeric,
    body_battery_min int,
    body_battery_max int,
    resting_hr       int,
    source           text        NOT NULL DEFAULT 'garmin',
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- body_composition: reconstructed from apple_health.map_body_composition().
-- Key columns for index: recorded_at.
CREATE TABLE IF NOT EXISTS public.body_composition (
    id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    recorded_at           timestamptz NOT NULL,
    weight_kg             numeric,
    body_fat_pct          numeric,
    lean_mass_kg          numeric,
    bmi                   numeric,
    skeletal_muscle_kg    numeric,
    bone_mass_kg          numeric,
    bmr_kcal              numeric,
    visceral_fat_grade    numeric,
    body_age              numeric,
    body_score            numeric,
    subcutaneous_fat_pct  numeric,
    protein_kg            numeric,
    body_water_kg         numeric,
    muscle_kg             numeric,
    body_fat_kg           numeric,
    fat_free_kg           numeric,
    source                text        NOT NULL DEFAULT 'apple_health',
    created_at            timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Add user_id to all 9 per-user tables
-- ---------------------------------------------------------------------------

ALTER TABLE public.health_logs            ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE public.sleep_session          ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE public.daily_stats            ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE public.body_composition       ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE public.medications            ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE public.habits                 ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE public.finance_transactions   ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE public.finance_category_cache ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE public.alert_emissions        ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES public.users(id) ON DELETE CASCADE;

-- ---------------------------------------------------------------------------
-- Indexes (composite where ordering/query pattern demands)
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS health_logs_user_id_recorded_at_idx   ON public.health_logs (user_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS sleep_session_user_id_start_idx       ON public.sleep_session (user_id, start_at DESC);
CREATE INDEX IF NOT EXISTS daily_stats_user_id_date_idx          ON public.daily_stats (user_id, date DESC);
CREATE INDEX IF NOT EXISTS body_composition_user_id_recorded_idx ON public.body_composition (user_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS medications_user_id_idx               ON public.medications (user_id);
CREATE INDEX IF NOT EXISTS habits_user_id_idx                    ON public.habits (user_id);
CREATE INDEX IF NOT EXISTS finance_transactions_user_id_ts_idx   ON public.finance_transactions (user_id, ts DESC);
CREATE INDEX IF NOT EXISTS alert_emissions_user_id_rule_idx      ON public.alert_emissions (user_id, rule_id);

-- ---------------------------------------------------------------------------
-- Unique constraints widened to include user_id
-- ---------------------------------------------------------------------------

DROP INDEX IF EXISTS medications_name_active_uniq;
CREATE UNIQUE INDEX IF NOT EXISTS medications_user_name_active_uniq
  ON public.medications (user_id, name) WHERE archived_at IS NULL;

DROP INDEX IF EXISTS habits_name_active_uniq;
CREATE UNIQUE INDEX IF NOT EXISTS habits_user_name_active_uniq
  ON public.habits (user_id, name) WHERE archived_at IS NULL;

ALTER TABLE public.finance_transactions DROP CONSTRAINT IF EXISTS finance_transactions_txn_id_key;
ALTER TABLE public.finance_transactions DROP CONSTRAINT IF EXISTS finance_transactions_user_txn_uniq;
ALTER TABLE public.finance_transactions ADD CONSTRAINT finance_transactions_user_txn_uniq UNIQUE (user_id, txn_id);

ALTER TABLE public.finance_category_cache DROP CONSTRAINT IF EXISTS finance_category_cache_pkey;
ALTER TABLE public.finance_category_cache ADD PRIMARY KEY (user_id, desc_key);

-- Widen health_logs natural-key uniqueness (from 0001_init) so HealthKit samples
-- of different users don't collide on (source, type, recorded_at).
DROP INDEX IF EXISTS health_logs_dedup_idx;
CREATE UNIQUE INDEX IF NOT EXISTS health_logs_user_source_type_recorded_uniq
  ON public.health_logs (user_id, source, type, recorded_at);
