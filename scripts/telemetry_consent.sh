#!/usr/bin/env bash
# Grant or revoke one user's consent to capture LLM bodies in telemetry.
set -euo pipefail
cd "$(dirname "$0")/.."
consent_user_id=${1:-}
if [[ ! "$consent_user_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
  echo "FAIL code=invalid_user_id" >&2
  exit 2
fi
consent_ok=true
[[ "${2:-}" == "off" ]] && consent_ok=false
if [[ -f .env ]]; then set -a; source .env; set +a; fi
if [[ -z "${APP_RW_PASSWORD:-}" || -z "${POSTGRES_DB:-}" ]]; then
  echo "FAIL code=database_not_configured" >&2
  exit 2
fi
if ! docker compose exec -T -e PGPASSWORD="$APP_RW_PASSWORD" postgres \
  psql -X -qAt -v ON_ERROR_STOP=1 -h localhost -U app_rw -d "$POSTGRES_DB" -c "
    BEGIN;
    SELECT set_config('app.user_id', '$consent_user_id', true);
    INSERT INTO telemetry_consent (user_id, bodies_ok, updated_at)
      VALUES ('$consent_user_id', $consent_ok, now())
      ON CONFLICT (user_id) DO UPDATE
      SET bodies_ok = EXCLUDED.bodies_ok, updated_at = now();
    COMMIT;" >/dev/null 2>&1; then
  echo "FAIL code=consent_write_failed id=$consent_user_id" >&2
  exit 1
fi
echo "PASS code=telemetry_consent id=$consent_user_id bodies_ok=$consent_ok"
