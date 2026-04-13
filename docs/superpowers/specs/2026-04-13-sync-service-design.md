# Sync Service — Design Spec
_Date: 2026-04-13_

## Overview

A `sync-service` Docker container that pulls data from Garmin Connect and writes normalized records into Postgres `health_logs`. Agents are source-agnostic — they only read from the DB, so this service integrates transparently with the existing system.

---

## 1. Architecture

### Container

A Python/FastAPI service that:
- Authenticates with Garmin Connect via the `garminconnect` library
- Runs a daily APScheduler job (06:00 UTC by default, configurable via `SYNC_HOUR` env var)
- Exposes `POST /sync` for on-demand triggering
- Exposes `GET /health` for Docker healthcheck
- Writes normalized records to `health_logs` in Postgres
- Deduplicates by `(source, type, recorded_at)` — on conflict, skip

### Deduplication Strategy

Each sync fetches the last 7 days of data. On insert, a unique constraint on `(source, type, recorded_at)` (added via migration) causes conflicts to be silently skipped (`ON CONFLICT DO NOTHING`). Garmin data does not change retroactively, so no upsert is needed.

### Credentials

`GARMIN_EMAIL` and `GARMIN_PASSWORD` are stored in `.env` and injected as environment variables. The service authenticates on each sync run (no persistent session storage needed for daily frequency).

### On-Demand Trigger Wiring

- `POST /sync` returns `{"synced": N, "skipped": M, "errors": [...]}`
- nginx proxy adds `/sync` → `http://sync-service` route
- Orchestrator gains `"sync"` / `"синхронизировать"` as an intent keyword → calls `POST http://sync-service/sync` and returns the summary as a chat message

---

## 2. File Structure

```
sync-service/
  app/
    main.py          # FastAPI app: /sync endpoint, /health, lifespan scheduler setup
    scheduler.py     # APScheduler daily job configuration
    garmin.py        # garminconnect client: auth + fetch sleep, activities, daily stats
    mapper.py        # Garmin API responses → health_logs row dicts
    db.py            # asyncpg pool + bulk insert with ON CONFLICT DO NOTHING
  requirements.txt
  Dockerfile
```

---

## 3. Data Mapping

All records: `source = 'garmin'`, `recorded_at` = the date/time the data represents.

### Sleep (`agent='sleep'`, `type='sleep_session'`)

```json
{
  "duration_seconds": 27180,
  "start_time": "2026-04-12T23:15:00",
  "end_time": "2026-04-13T06:48:00",
  "score": 82,
  "deep_sleep_seconds": 5400,
  "rem_sleep_seconds": 6300,
  "light_sleep_seconds": 12600,
  "awake_seconds": 2880,
  "hrv_weekly_avg": 54
}
```

### Activity / Workout (`agent='workout'`, `type='activity'`)

```json
{
  "activity_type": "running",
  "name": "Morning Run",
  "duration_seconds": 2580,
  "distance_meters": 5240,
  "calories": 412,
  "avg_hr": 158,
  "max_hr": 181,
  "garmin_activity_id": 12345678
}
```

### Daily Stats (`agent='sleep'`, `type='daily_stats'`)

Body battery, HRV, and resting HR are most relevant to sleep analysis, so daily stats are attributed to the sleep agent.

```json
{
  "steps": 9823,
  "calories_active": 620,
  "stress_avg": 28,
  "body_battery_min": 14,
  "body_battery_max": 87,
  "resting_hr": 52
}
```

---

## 4. DB Migration

Add a unique constraint to `health_logs` to enable deduplication:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS health_logs_source_type_recorded_at_uniq
  ON health_logs (source, type, recorded_at);
```

This migration is appended to `db/init.sql`. `CREATE UNIQUE INDEX IF NOT EXISTS` is idempotent and safe to re-run.

---

## 5. Error Handling

| Failure | Behaviour |
|---|---|
| Garmin auth failure | Log error, return 503, do not crash scheduler |
| One data type fails (e.g. sleep API down) | Log, continue with remaining types, report in response |
| DB write failure | Log, report in response, do not retry (next scheduled run will cover it) |
| Garmin returns empty data for a day | Skip silently — normal for days with no activity |

---

## 6. Testing

**Unit tests (`tests/test_sync_mapper.py`):**
- Fixed Garmin API response dicts → expected `health_logs` row shapes
- No network, no DB required
- Covers sleep, activity, and daily stats mappers
- Covers missing/null fields (Garmin sometimes omits optional fields)

**Integration tests (`tests/test_sync_endpoint.py`):**
- Mock `garminconnect` client with fixture data
- Mock asyncpg pool
- `POST /sync` → assert correct rows inserted
- `POST /sync` with duplicate data → assert `skipped` count correct, no DB errors

---

## 7. Docker & Compose

`sync-service/Dockerfile`: standard Python 3.12-slim, no build complexity.

Addition to `docker-compose.yml`:
```yaml
sync-service:
  build: ./sync-service
  environment:
    POSTGRES_DSN: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    GARMIN_EMAIL: ${GARMIN_EMAIL}
    GARMIN_PASSWORD: ${GARMIN_PASSWORD}
    SYNC_HOUR: "6"
  depends_on:
    postgres:
      condition: service_healthy
  restart: unless-stopped
```

nginx addition (in `agui-frontend/nginx.conf`):
```nginx
location /sync {
    proxy_pass http://sync-service;
}
```

Orchestrator addition: `"sync"` / `"синхронизировать"` intent keywords → `POST http://sync-service/sync` → return summary string.

---

## 8. Out of Scope

- Apple Health, Strava, or other integrations (can be added to `garmin.py`'s pattern later)
- Backfill beyond 7 days on first run (run `/sync` manually a few times if needed)
- Persistent Garmin session tokens (re-auth on each sync is fine for daily frequency)
- Webhook/push from Garmin (pull-based is sufficient)
