# Sync Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `sync_service` Docker container that pulls the last 7 days of Garmin Connect data (sleep, activities, daily stats) into Postgres `health_logs` on a daily schedule and on demand via `POST /sync`.

**Architecture:** A Python/FastAPI service with APScheduler runs daily at 06:00 UTC. `POST /sync` is also exposed for on-demand triggering. The orchestrator gains a "sync" intent that calls it. nginx proxies `/sync` from the frontend. All sync logic is source-agnostic from the agents' perspective — they only read `health_logs`.

**Tech Stack:** Python 3.12, FastAPI, garminconnect, APScheduler 3.x, asyncpg, pytest-asyncio.

---

## File Map

### New files

| File | Responsibility |
|---|---|
| `sync_service/__init__.py` | Makes `sync_service` a Python package (importable in tests) |
| `sync_service/app/__init__.py` | Makes `app` a sub-package |
| `sync_service/app/mapper.py` | Pure functions: Garmin API dicts → `health_logs` row dicts |
| `sync_service/app/db.py` | asyncpg pool + `insert_rows()` with `ON CONFLICT DO NOTHING` |
| `sync_service/app/garmin.py` | garminconnect wrapper: authenticate + fetch all data types |
| `sync_service/app/sync.py` | `do_sync()` — orchestrates garmin fetch + map + db write |
| `sync_service/app/scheduler.py` | APScheduler setup: daily job calling `do_sync()` |
| `sync_service/app/main.py` | FastAPI app: `/sync`, `/health`, lifespan with scheduler |
| `sync_service/requirements.txt` | Python dependencies |
| `sync_service/Dockerfile` | Container build |
| `tests/test_sync_mapper.py` | Unit tests for mapper.py (no network, no DB) |
| `tests/test_sync_endpoint.py` | Integration test for POST /sync (mocked garmin + mocked DB) |

### Modified files

| File | Change |
|---|---|
| `db/init.sql` | Add unique index on `health_logs(source, type, recorded_at)` |
| `docker-compose.yml` | Add `sync-service` service |
| `agui-frontend/nginx.conf` | Proxy `/sync` to sync-service |
| `orchestrator/app/router.py` | Add `"sync"` intent keywords |
| `orchestrator/app/main.py` | Handle `"sync"` intent in `/chat` and `/chat/stream` |

---

## Task 1: DB migration — unique index on health_logs

**Files:**
- Modify: `db/init.sql`

- [ ] **Step 1: Add unique index to init.sql**

Append to the end of `db/init.sql`:
```sql
CREATE UNIQUE INDEX IF NOT EXISTS health_logs_dedup_idx
  ON health_logs (source, type, recorded_at);
```

- [ ] **Step 2: Verify SQL is valid**

```bash
docker run --rm postgres:16-alpine psql --help > /dev/null && echo "postgres available"
```

If you have postgres running locally you can test the SQL; otherwise proceed — the index will be created when docker compose initialises the DB.

- [ ] **Step 3: Commit**

```bash
git add db/init.sql
git commit -m "feat: add deduplication index on health_logs(source, type, recorded_at)"
```

---

## Task 2: mapper.py — Garmin responses → health_logs rows (TDD)

**Files:**
- Create: `sync_service/__init__.py`
- Create: `sync_service/app/__init__.py`
- Create: `tests/test_sync_mapper.py`
- Create: `sync_service/app/mapper.py`

- [ ] **Step 1: Create package init files**

```bash
mkdir -p sync_service/app
touch sync_service/__init__.py sync_service/app/__init__.py
```

- [ ] **Step 2: Write failing tests**

`tests/test_sync_mapper.py`:
```python
from datetime import datetime, timezone
import pytest
from sync_service.app.mapper import map_sleep, map_activity, map_daily_stats

SLEEP_RAW = {
    "dailySleepDTO": {
        "sleepTimeSeconds": 27180,
        "deepSleepSeconds": 5400,
        "lightSleepSeconds": 12600,
        "remSleepSeconds": 6300,
        "awakeSleepSeconds": 2880,
        "sleepStartTimestampLocal": 1744506900000,
        "sleepEndTimestampLocal": 1744531680000,
        "sleepScores": {"overall": {"value": 82}},
        "averageHRV": 54,
    }
}

ACTIVITY_RAW = {
    "activityId": 12345678,
    "activityName": "Morning Run",
    "activityType": {"typeKey": "running"},
    "duration": 2580.0,
    "distance": 5240.0,
    "calories": 412,
    "averageHR": 158,
    "maxHR": 181,
    "startTimeLocal": "2026-04-13 07:00:00",
}

STATS_RAW = {
    "totalSteps": 9823,
    "activeKilocalories": 620,
    "averageStressLevel": 28,
    "minBodyBattery": 14,
    "maxBodyBattery": 87,
    "restingHeartRate": 52,
}


def test_map_sleep_basic():
    row = map_sleep("2026-04-13", SLEEP_RAW)
    assert row is not None
    assert row["agent"] == "sleep"
    assert row["type"] == "sleep_session"
    assert row["source"] == "garmin"
    assert row["data"]["duration_seconds"] == 27180
    assert row["data"]["deep_sleep_seconds"] == 5400
    assert row["data"]["rem_sleep_seconds"] == 6300
    assert row["data"]["light_sleep_seconds"] == 12600
    assert row["data"]["awake_seconds"] == 2880
    assert row["data"]["score"] == 82
    assert row["data"]["hrv_weekly_avg"] == 54
    assert isinstance(row["recorded_at"], datetime)
    assert row["recorded_at"].tzinfo is not None


def test_map_sleep_missing_dto_returns_none():
    assert map_sleep("2026-04-13", {}) is None


def test_map_sleep_missing_start_returns_none():
    assert map_sleep("2026-04-13", {"dailySleepDTO": {}}) is None


def test_map_sleep_missing_optional_fields():
    raw = {
        "dailySleepDTO": {
            "sleepTimeSeconds": 25200,
            "sleepStartTimestampLocal": 1744506900000,
        }
    }
    row = map_sleep("2026-04-13", raw)
    assert row is not None
    assert row["data"]["score"] is None
    assert row["data"]["hrv_weekly_avg"] is None
    assert row["data"]["deep_sleep_seconds"] == 0


def test_map_activity_basic():
    row = map_activity(ACTIVITY_RAW)
    assert row is not None
    assert row["agent"] == "workout"
    assert row["type"] == "activity"
    assert row["source"] == "garmin"
    assert row["data"]["activity_type"] == "running"
    assert row["data"]["name"] == "Morning Run"
    assert row["data"]["duration_seconds"] == 2580
    assert row["data"]["distance_meters"] == 5240
    assert row["data"]["calories"] == 412
    assert row["data"]["avg_hr"] == 158
    assert row["data"]["max_hr"] == 181
    assert row["data"]["garmin_activity_id"] == 12345678
    assert isinstance(row["recorded_at"], datetime)
    assert row["recorded_at"].tzinfo is not None


def test_map_activity_missing_start_returns_none():
    assert map_activity({"activityName": "Run"}) is None


def test_map_activity_missing_optional_fields():
    raw = {"startTimeLocal": "2026-04-13 07:00:00"}
    row = map_activity(raw)
    assert row is not None
    assert row["data"]["activity_type"] == "unknown"
    assert row["data"]["avg_hr"] is None
    assert row["data"]["max_hr"] is None


def test_map_daily_stats_basic():
    row = map_daily_stats("2026-04-13", STATS_RAW)
    assert row is not None
    assert row["agent"] == "sleep"
    assert row["type"] == "daily_stats"
    assert row["source"] == "garmin"
    assert row["data"]["steps"] == 9823
    assert row["data"]["calories_active"] == 620
    assert row["data"]["stress_avg"] == 28
    assert row["data"]["body_battery_min"] == 14
    assert row["data"]["body_battery_max"] == 87
    assert row["data"]["resting_hr"] == 52
    assert isinstance(row["recorded_at"], datetime)
    assert row["recorded_at"].tzinfo is not None


def test_map_daily_stats_empty_returns_none():
    assert map_daily_stats("2026-04-13", {}) is None


def test_map_daily_stats_none_returns_none():
    assert map_daily_stats("2026-04-13", None) is None
```

- [ ] **Step 3: Run tests to confirm they fail**

```bash
pytest tests/test_sync_mapper.py -v
```
Expected: `ImportError` — `sync_service.app.mapper` doesn't exist yet.

- [ ] **Step 4: Create `sync_service/app/mapper.py`**

```python
from datetime import datetime, timezone


def map_sleep(date_str: str, raw: dict) -> dict | None:
    """Map Garmin get_sleep_data() response to a health_logs row dict."""
    dto = raw.get("dailySleepDTO", {})
    if not dto:
        return None
    start_ms = dto.get("sleepStartTimestampLocal")
    if start_ms is None:
        return None

    scores = dto.get("sleepScores", {})
    overall = scores.get("overall", {})
    score = overall.get("value") if isinstance(overall, dict) else None

    return {
        "agent": "sleep",
        "type": "sleep_session",
        "data": {
            "duration_seconds": dto.get("sleepTimeSeconds", 0),
            "start_time": datetime.fromtimestamp(start_ms / 1000).isoformat(),
            "end_time": datetime.fromtimestamp(
                dto.get("sleepEndTimestampLocal", start_ms) / 1000
            ).isoformat(),
            "score": score,
            "deep_sleep_seconds": dto.get("deepSleepSeconds", 0),
            "rem_sleep_seconds": dto.get("remSleepSeconds", 0),
            "light_sleep_seconds": dto.get("lightSleepSeconds", 0),
            "awake_seconds": dto.get("awakeSleepSeconds", 0),
            "hrv_weekly_avg": dto.get("averageHRV"),
        },
        "recorded_at": datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc),
        "source": "garmin",
    }


def map_activity(raw: dict) -> dict | None:
    """Map a single Garmin activity dict to a health_logs row dict."""
    start_str = raw.get("startTimeLocal")
    if not start_str:
        return None

    recorded_at = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
    activity_type = raw.get("activityType", {})
    type_key = (
        activity_type.get("typeKey", "unknown")
        if isinstance(activity_type, dict)
        else "unknown"
    )

    return {
        "agent": "workout",
        "type": "activity",
        "data": {
            "activity_type": type_key,
            "name": raw.get("activityName", ""),
            "duration_seconds": int(raw.get("duration", 0)),
            "distance_meters": int(raw.get("distance", 0)),
            "calories": raw.get("calories", 0),
            "avg_hr": raw.get("averageHR"),
            "max_hr": raw.get("maxHR"),
            "garmin_activity_id": raw.get("activityId"),
        },
        "recorded_at": recorded_at,
        "source": "garmin",
    }


def map_daily_stats(date_str: str, raw: dict | None) -> dict | None:
    """Map Garmin get_stats() response to a health_logs row dict."""
    if not raw:
        return None

    recorded_at = datetime.fromisoformat(f"{date_str}T12:00:00").replace(
        tzinfo=timezone.utc
    )
    return {
        "agent": "sleep",
        "type": "daily_stats",
        "data": {
            "steps": raw.get("totalSteps", 0),
            "calories_active": raw.get("activeKilocalories", 0),
            "stress_avg": raw.get("averageStressLevel"),
            "body_battery_min": raw.get("minBodyBattery"),
            "body_battery_max": raw.get("maxBodyBattery"),
            "resting_hr": raw.get("restingHeartRate"),
        },
        "recorded_at": recorded_at,
        "source": "garmin",
    }
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_sync_mapper.py -v
```
Expected: all 10 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add sync_service/ tests/test_sync_mapper.py
git commit -m "feat: add sync service mapper with unit tests"
```

---

## Task 3: db.py — asyncpg insert with deduplication

**Files:**
- Create: `sync_service/app/db.py`

- [ ] **Step 1: Create `sync_service/app/db.py`**

```python
import asyncpg
import json
import os

_pool: asyncpg.Pool | None = None


async def _set_json_codec(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.environ["POSTGRES_DSN"], init=_set_json_codec
        )
    return _pool


async def insert_rows(rows: list[dict]) -> tuple[int, int]:
    """Insert health_logs rows. Skips duplicates via unique index.
    Returns (inserted, skipped).
    """
    if not rows:
        return 0, 0
    pool = await get_pool()
    inserted = 0
    skipped = 0
    async with pool.acquire() as conn:
        for row in rows:
            result = await conn.execute(
                """
                INSERT INTO health_logs (agent, type, data, recorded_at, source)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (source, type, recorded_at) DO NOTHING
                """,
                row["agent"],
                row["type"],
                row["data"],
                row["recorded_at"],
                row["source"],
            )
            # result string is "INSERT 0 1" (inserted) or "INSERT 0 0" (skipped)
            if result.endswith("1"):
                inserted += 1
            else:
                skipped += 1
    return inserted, skipped
```

- [ ] **Step 2: Commit**

```bash
git add sync_service/app/db.py
git commit -m "feat: add sync service db module with dedup insert"
```

---

## Task 4: garmin.py — garminconnect wrapper

**Files:**
- Create: `sync_service/app/garmin.py`

- [ ] **Step 1: Create `sync_service/app/garmin.py`**

```python
import asyncio
import os
from datetime import date, timedelta

from garminconnect import Garmin


def _get_dates(days: int = 7) -> list[str]:
    """Return ISO date strings for the last N days, newest first."""
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(days)]


def _fetch_sync(days: int) -> dict:
    """Synchronous Garmin fetch — called via asyncio.to_thread."""
    client = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
    client.login()

    dates = _get_dates(days)
    sleep_data: list[tuple[str, dict]] = []
    activities: list[dict] = []
    daily_stats: list[tuple[str, dict]] = []
    errors: list[str] = []

    for d in dates:
        try:
            sleep_data.append((d, client.get_sleep_data(d)))
        except Exception as e:
            errors.append(f"sleep {d}: {e}")

    try:
        # Activities: single range call, newest-first dates so [-1] is oldest
        activities = client.get_activities_by_date(dates[-1], dates[0])
    except Exception as e:
        errors.append(f"activities: {e}")

    for d in dates:
        try:
            daily_stats.append((d, client.get_stats(d)))
        except Exception as e:
            errors.append(f"daily_stats {d}: {e}")

    return {
        "sleep": sleep_data,
        "activities": activities,
        "daily_stats": daily_stats,
        "errors": errors,
    }


async def fetch_all(days: int = 7) -> dict:
    """Async wrapper: runs the blocking Garmin client in a thread pool."""
    return await asyncio.to_thread(_fetch_sync, days)
```

- [ ] **Step 2: Commit**

```bash
git add sync_service/app/garmin.py
git commit -m "feat: add Garmin Connect client wrapper"
```

---

## Task 5: sync.py + scheduler.py + main.py

**Files:**
- Create: `sync_service/app/sync.py`
- Create: `sync_service/app/scheduler.py`
- Create: `sync_service/app/main.py`

- [ ] **Step 1: Create `sync_service/app/sync.py`**

```python
from .garmin import fetch_all
from .mapper import map_sleep, map_activity, map_daily_stats
from .db import insert_rows


async def do_sync(days: int = 7) -> dict:
    """Fetch all Garmin data, map to health_logs rows, insert with dedup.
    Returns {"synced": int, "skipped": int, "errors": list[str]}.
    """
    raw = await fetch_all(days)
    rows: list[dict] = []
    errors: list[str] = list(raw["errors"])

    for date_str, sleep_raw in raw["sleep"]:
        row = map_sleep(date_str, sleep_raw)
        if row:
            rows.append(row)

    for activity_raw in raw["activities"]:
        row = map_activity(activity_raw)
        if row:
            rows.append(row)

    for date_str, stats_raw in raw["daily_stats"]:
        row = map_daily_stats(date_str, stats_raw)
        if row:
            rows.append(row)

    try:
        inserted, skipped = await insert_rows(rows)
    except Exception as e:
        errors.append(f"db: {e}")
        inserted, skipped = 0, 0

    return {"synced": inserted, "skipped": skipped, "errors": errors}
```

- [ ] **Step 2: Create `sync_service/app/scheduler.py`**

```python
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def start_scheduler() -> None:
    hour = int(os.environ.get("SYNC_HOUR", "6"))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_daily_sync,
        CronTrigger(hour=hour, minute=0),
        id="daily_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(f"Scheduler started: daily sync at {hour:02d}:00 UTC")


async def _run_daily_sync() -> None:
    from .sync import do_sync  # late import to avoid circular at module load

    try:
        result = await do_sync()
        logger.info(f"Daily sync complete: {result}")
    except Exception as e:
        logger.error(f"Daily sync failed: {e}")
```

- [ ] **Step 3: Create `sync_service/app/main.py`**

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .scheduler import start_scheduler
from .sync import do_sync

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield


app = FastAPI(title="sync-service", lifespan=lifespan)


@app.post("/sync")
async def sync():
    return await do_sync()


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 4: Commit**

```bash
git add sync_service/app/sync.py sync_service/app/scheduler.py sync_service/app/main.py
git commit -m "feat: add sync orchestration, scheduler, and FastAPI app"
```

---

## Task 6: requirements.txt + Dockerfile

**Files:**
- Create: `sync_service/requirements.txt`
- Create: `sync_service/Dockerfile`

- [ ] **Step 1: Create `sync_service/requirements.txt`**

```
fastapi>=0.111
uvicorn[standard]>=0.29
asyncpg>=0.29
garminconnect>=0.2.19
apscheduler>=3.10
```

- [ ] **Step 2: Create `sync_service/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 3: Verify Docker build**

```bash
cd sync_service && docker build -t sync-service-test .
```
Expected: image builds successfully.

- [ ] **Step 4: Commit**

```bash
cd ..
git add sync_service/requirements.txt sync_service/Dockerfile
git commit -m "feat: add sync service Dockerfile and requirements"
```

---

## Task 7: docker-compose.yml + nginx.conf

**Files:**
- Modify: `docker-compose.yml`
- Modify: `agui-frontend/nginx.conf`

- [ ] **Step 1: Add sync-service to docker-compose.yml**

In `docker-compose.yml`, add this service block before the `volumes:` section:
```yaml
  sync-service:
    build: ./sync_service
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

- [ ] **Step 2: Add GARMIN_EMAIL and GARMIN_PASSWORD to .env**

```bash
echo "GARMIN_EMAIL=your@email.com" >> .env
echo "GARMIN_PASSWORD=yourpassword" >> .env
```

Replace with your real Garmin credentials. `.env` is already in `.gitignore`.

- [ ] **Step 3: Add /sync proxy to agui-frontend/nginx.conf**

In `agui-frontend/nginx.conf`, add this location block before the SPA fallback `location /` block:
```nginx
    location /sync {
        proxy_pass http://sync-service:8080;
    }
```

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml agui-frontend/nginx.conf
git commit -m "feat: add sync-service to docker-compose and nginx proxy"
```

---

## Task 8: Orchestrator sync intent

**Files:**
- Modify: `orchestrator/app/router.py`
- Modify: `orchestrator/app/main.py`

- [ ] **Step 1: Write failing test for sync routing**

Add to `tests/test_orchestrator_routing.py`:
```python
def test_classify_sync_intent():
    assert classify_intent("sync") == "sync"
    assert classify_intent("синхронизировать гармин") == "sync"
    assert classify_intent("garmin sync") == "sync"
    assert classify_intent("гармин") == "sync"
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/test_orchestrator_routing.py::test_classify_sync_intent -v
```
Expected: FAIL — `classify_intent("sync")` returns `"sleep"` (default).

- [ ] **Step 3: Add "sync" to INTENT_KEYWORDS in router.py**

Replace the entire `INTENT_KEYWORDS` dict in `orchestrator/app/router.py`:
```python
INTENT_KEYWORDS: dict[str, list[str]] = {
    "sleep": ["sleep", "спал", "сон", "засыпал", "проснул", "ночь"],
    "workout": ["workout", "трениров", "пробеж", "run", "exercise", "спорт", "фитнес"],
    "nutrition": ["nutrition", "еда", "ел", "питание", "meal", "food", "калори"],
    "sync": ["sync", "синхронизир", "garmin", "гармин"],
}
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
pytest tests/test_orchestrator_routing.py -v
```
Expected: all tests PASS including `test_classify_sync_intent`.

- [ ] **Step 5: Write failing test for sync endpoint handling**

Add to `tests/test_orchestrator_stats.py`:
```python
@pytest.mark.asyncio
async def test_chat_stream_sync_intent_calls_sync_service():
    """POST /chat/stream with sync intent calls sync-service and streams result."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"synced": 5, "skipped": 2, "errors": []})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("orchestrator.app.main.classify_intent", return_value="sync"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            from orchestrator.app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/chat/stream", json={
                    "messages": [{"role": "user", "content": "sync garmin"}],
                })

    assert resp.status_code == 200
    events = parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types[0] == "RunStarted"
    assert types[-1] == "RunFinished"
    content_events = [e for e in events if e["type"] == "TextMessageContent"]
    full_text = "".join(e["delta"] for e in content_events)
    assert "5" in full_text  # synced count
```

(`parse_sse` is already defined in `test_orchestrator_stream.py` — import it or copy the definition.)

Replace the import block at the top of `tests/test_orchestrator_stats.py` to add:
```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
import json


def parse_sse(raw: str) -> list[dict]:
    events = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events
```

- [ ] **Step 6: Run test to confirm failure**

```bash
pytest tests/test_orchestrator_stats.py::test_chat_stream_sync_intent_calls_sync_service -v
```
Expected: FAIL — `classify_intent("sync garmin")` returns `"sync"` but the orchestrator treats it as an unknown agent and returns 503.

- [ ] **Step 7: Update orchestrator/app/main.py to handle sync intent**

In `orchestrator/app/main.py`, add the sync handler inside `chat_stream` just after the `agent_name` is classified. The full updated `chat_stream` function:

```python
@app.post("/chat/stream")
async def chat_stream(req: StreamChatRequest):
    user_messages = [m for m in req.messages if m.get("role") == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    message = user_messages[-1].get("content", "")

    thread_id = req.threadId or str(uuid.uuid4())
    run_id = req.runId or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    agent_name = classify_intent(message)

    if agent_name == "sync":
        async def sync_stream():
            yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
            yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post("http://sync-service:8080/sync")
                    resp.raise_for_status()
                    data = resp.json()
                    text = f"Sync complete: {data['synced']} records synced, {data['skipped']} skipped."
                    if data.get("errors"):
                        text += f" Errors: {'; '.join(data['errors'][:3])}"
            except Exception as e:
                text = f"Sync failed: {str(e)}"
            yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": text})
            yield _sse({"type": "TextMessageEnd", "messageId": message_id})
            yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})

        return StreamingResponse(
            sync_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    agent_url = get_agent_url(agent_name)

    async def event_stream():
        yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
        yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})

        if not agent_url:
            error_text = f"Agent '{agent_name}' is not available."
            yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": error_text})
            yield _sse({"type": "TextMessageEnd", "messageId": message_id})
            yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})
            return

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{agent_url}/tasks",
                    json={"task": AGENT_DEFAULT_TASK.get(agent_name, f"analyze_{agent_name}"), "params": {"message": message}},
                )
                resp.raise_for_status()
                output = resp.json().get("output", "")
        except Exception as e:
            output = f"Error contacting agent: {str(e)}"

        for chunk in _split_chunks(output, size=5):
            yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": chunk})
            await asyncio.sleep(0.02)

        yield _sse({"type": "TextMessageEnd", "messageId": message_id})
        yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

Also update the `/chat` (Telegram) endpoint to handle sync intent. Replace the `/chat` handler:

```python
@app.post("/chat")
async def chat(req: ChatRequest):
    agent_name = classify_intent(req.message)

    if agent_name == "sync":
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post("http://sync-service:8080/sync")
                resp.raise_for_status()
                data = resp.json()
                text = f"Sync complete: {data['synced']} records synced, {data['skipped']} skipped."
                if data.get("errors"):
                    text += f" Errors: {'; '.join(data['errors'][:3])}"
            return {"output": text}
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Sync service error: {str(e)}")

    agent_url = get_agent_url(agent_name)
    if not agent_url:
        raise HTTPException(
            status_code=503,
            detail=f"Agent '{agent_name}' is not available. Available: {list_agents()}"
        )

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(
                f"{agent_url}/tasks",
                json={"task": AGENT_DEFAULT_TASK.get(agent_name, f"analyze_{agent_name}"), "params": {"message": req.message}},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Agent '{agent_name}' error: {e.response.text[:500]}",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Could not reach agent '{agent_name}': {str(e)}",
            )
```

- [ ] **Step 8: Run all orchestrator tests**

```bash
pytest tests/test_orchestrator_routing.py tests/test_orchestrator_stats.py tests/test_orchestrator_stream.py -v
```
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add orchestrator/app/router.py orchestrator/app/main.py tests/test_orchestrator_routing.py tests/test_orchestrator_stats.py
git commit -m "feat: add sync intent routing to orchestrator"
```

---

## Task 9: Integration test for /sync endpoint

**Files:**
- Create: `tests/test_sync_endpoint.py`

- [ ] **Step 1: Write integration tests**

`tests/test_sync_endpoint.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport


MOCK_GARMIN_DATA = {
    "sleep": [
        ("2026-04-13", {
            "dailySleepDTO": {
                "sleepTimeSeconds": 27180,
                "deepSleepSeconds": 5400,
                "lightSleepSeconds": 12600,
                "remSleepSeconds": 6300,
                "awakeSleepSeconds": 2880,
                "sleepStartTimestampLocal": 1744506900000,
                "sleepEndTimestampLocal": 1744531680000,
                "sleepScores": {"overall": {"value": 82}},
                "averageHRV": 54,
            }
        }),
    ],
    "activities": [
        {
            "activityId": 12345678,
            "activityName": "Morning Run",
            "activityType": {"typeKey": "running"},
            "duration": 2580.0,
            "distance": 5240.0,
            "calories": 412,
            "averageHR": 158,
            "maxHR": 181,
            "startTimeLocal": "2026-04-13 07:00:00",
        }
    ],
    "daily_stats": [
        ("2026-04-13", {
            "totalSteps": 9823,
            "activeKilocalories": 620,
            "averageStressLevel": 28,
            "minBodyBattery": 14,
            "maxBodyBattery": 87,
            "restingHeartRate": 52,
        }),
    ],
    "errors": [],
}


@pytest.mark.asyncio
async def test_sync_endpoint_inserts_and_returns_counts():
    """POST /sync maps Garmin data and writes to DB, returns synced/skipped counts."""
    with patch("sync_service.app.sync.fetch_all", new=AsyncMock(return_value=MOCK_GARMIN_DATA)):
        with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(3, 0))):
            from sync_service.app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/sync")

    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] == 3
    assert body["skipped"] == 0
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_sync_endpoint_dedup_skips():
    """POST /sync with duplicate data reports skipped count."""
    with patch("sync_service.app.sync.fetch_all", new=AsyncMock(return_value=MOCK_GARMIN_DATA)):
        with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(0, 3))):
            from sync_service.app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/sync")

    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] == 0
    assert body["skipped"] == 3


@pytest.mark.asyncio
async def test_sync_endpoint_garmin_errors_reported():
    """POST /sync propagates Garmin fetch errors in response."""
    data_with_error = {**MOCK_GARMIN_DATA, "errors": ["sleep 2026-04-12: timeout"]}
    with patch("sync_service.app.sync.fetch_all", new=AsyncMock(return_value=data_with_error)):
        with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(2, 0))):
            from sync_service.app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/sync")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["errors"]) == 1
    assert "sleep 2026-04-12" in body["errors"][0]


@pytest.mark.asyncio
async def test_health_endpoint():
    from sync_service.app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_sync_endpoint.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_sync_endpoint.py
git commit -m "test: add sync endpoint integration tests"
```

---

## Task 10: Full test suite + smoke test

- [ ] **Step 1: Run all Python tests**

```bash
pytest tests/ -v
```
Expected: all tests PASS (mapper, endpoint, orchestrator routing, stats, stream tests).

- [ ] **Step 2: Run all frontend tests**

```bash
cd agui-frontend && npm test
```
Expected: all 8 tests PASS.

- [ ] **Step 3: Start the full stack**

```bash
cd ..
source scripts/export-auth.sh
docker compose up --build
```
Expected: all containers start including `sync-service`.

- [ ] **Step 4: Trigger a sync via curl**

```bash
curl -s -X POST http://localhost:8080/sync | python3 -m json.tool
```
Expected output shape:
```json
{
  "synced": 21,
  "skipped": 0,
  "errors": []
}
```
If Garmin credentials are wrong: `{"synced": 0, "skipped": 0, "errors": ["activities: ...", ...]}`. Fix credentials in `.env` and retry.

- [ ] **Step 5: Trigger sync via chat**

In the frontend at `http://localhost:3000`, type: `sync garmin`
Expected: chat response like "Sync complete: 21 records synced, 0 skipped."

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: Plan 5 complete — Garmin sync service"
```
