#!/usr/bin/env bash
# scripts/migrate-to-supabase.sh — one-shot data move from local docker postgres into Supabase.
# Run ONCE during the cutover from single-user local postgres to multi-user Supabase.
set -euo pipefail
: "${OWNER_USER_ID:?set OWNER_USER_ID in .env.local — your Supabase auth.users UUID}"
: "${POSTGRES_DSN:?set POSTGRES_DSN in .env.local — the Supabase pooler url}"

LOCAL_DSN="${LOCAL_DSN:-postgresql://postgres:postgres@localhost:5432/life}"
DUMP=/tmp/life-agents-$(date -u +%Y%m%dT%H%M%SZ).dump

echo "==> Dumping local postgres → $DUMP"
pg_dump --data-only --no-owner --format=custom \
        --exclude-table=schema_migrations \
        --exclude-table=oauth_state \
        "$LOCAL_DSN" > "$DUMP"

echo "==> Restoring into Supabase (data only)"
pg_restore --data-only --no-owner --disable-triggers \
           --dbname="$POSTGRES_DSN" "$DUMP"

echo "==> Backfilling user_id"
psql "$POSTGRES_DSN" <<SQL
BEGIN;
UPDATE public.health_logs            SET user_id = '$OWNER_USER_ID' WHERE user_id IS NULL;
UPDATE public.sleep_session          SET user_id = '$OWNER_USER_ID' WHERE user_id IS NULL;
UPDATE public.daily_stats            SET user_id = '$OWNER_USER_ID' WHERE user_id IS NULL;
UPDATE public.body_composition       SET user_id = '$OWNER_USER_ID' WHERE user_id IS NULL;
UPDATE public.medications            SET user_id = '$OWNER_USER_ID' WHERE user_id IS NULL;
UPDATE public.habits                 SET user_id = '$OWNER_USER_ID' WHERE user_id IS NULL;
UPDATE public.finance_transactions   SET user_id = '$OWNER_USER_ID' WHERE user_id IS NULL;
UPDATE public.finance_category_cache SET user_id = '$OWNER_USER_ID' WHERE user_id IS NULL;
UPDATE public.alert_emissions        SET user_id = '$OWNER_USER_ID' WHERE user_id IS NULL;
COMMIT;
SQL

echo "==> Flipping columns to NOT NULL"
psql "$POSTGRES_DSN" <<SQL
ALTER TABLE public.health_logs            ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.sleep_session          ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.daily_stats            ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.body_composition       ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.medications            ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.habits                 ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.finance_transactions   ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.finance_category_cache ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.alert_emissions        ALTER COLUMN user_id SET NOT NULL;
SQL

echo "==> Running Qdrant tenancy migration"
python3 scripts/migrate-qdrant-tenancy.py

echo "✓ Done. Data migrated, user_id columns flipped NOT NULL."
