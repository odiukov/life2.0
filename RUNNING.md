# Running Life Agents

## Prerequisites

- Docker Desktop (or OrbStack / Colima) installed and running
- An API key for one of the supported LLM providers (OpenRouter by default — see `.env.example`)

## First-time Setup

1. Clone or navigate to the project directory
2. Copy environment file:
   ```bash
   cp .env.example .env
   ```

## LLM provider

Set `LLM_PROVIDER` in `.env` to one of: `anthropic`, `openrouter`, `gemini`,
`groq`, `ollama`. Default is `openrouter` with a free model. Set the
matching API key.

- **OpenRouter / Anthropic / Gemini:** just set the API key. Plain HTTP.
- **Groq:** just set `GROQ_API_KEY`. Free tier is ~30 req/min, ~14 400 req/day across Llama 3.x models — the most generous free option for tool-calling workloads. Get a key at https://console.groq.com/keys.
- **Ollama:** run Ollama on the host; set `OLLAMA_HOST=http://host.docker.internal:11434`.

Switch providers with a single env change + `docker compose restart`.

> **Note:** changing `LLM_PROVIDER` or `LLM_MODEL` in `.env` requires
> `docker compose up -d --force-recreate <service>` — a plain
> `docker compose restart` does not re-read `env_file`.

## Start the System

```bash
docker compose up --build -d
```

Wait ~60 seconds for all services to become healthy.

## Verify Everything is Running

```bash
# All services should show as healthy
docker compose ps

# Orchestrator discovered the sleep agent
curl http://localhost:8000/agents

# Send a test message
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Как я спал на этой неделе?"}'
```

Expected response from /agents:

```json
{ "agents": ["sleep"] }
```

Expected response from /chat:

```json
{ "status": "completed", "output": "...Claude's response..." }
```

## Verify Data Was Logged

```bash
docker compose exec postgres psql -U lifeagents -d lifeagents \
  -c "SELECT agent, task_type, output, created_at FROM tasks ORDER BY created_at DESC LIMIT 3;"
```

### LangGraph checkpoints

The orchestrator persists in-flight conversation state (per `threadId`) to
four LangGraph-managed tables: `checkpoints`, `checkpoint_blobs`,
`checkpoint_writes`, `checkpoint_migrations`. LangGraph owns the schema —
`AsyncPostgresSaver.setup()` creates them on first orchestrator startup.

This means `docker compose restart orchestrator` **preserves** an ongoing
conversation: sending a follow-up message on the same `threadId` resumes
from the last checkpoint instead of starting fresh. Quick verification:

```bash
./scripts/smoke-checkpointer.sh
```

The AG-UI frontend still loses `threadId` on page reload — refreshing the
tab starts a new conversation by design. Persisting it on the client is a
separate follow-up.

## Logs

```bash
docker compose logs -f orchestrator
docker compose logs -f agent-sleep
```

## Stop

```bash
docker compose down
```

## Architecture

```
[You] → curl/Browser
  ↓
[Orchestrator :8000] → classify intent → route via A2A
  ↓
[Sleep Agent :8001] → build prompt → LLM provider → store in DB/Qdrant
  ↓
[Postgres :5432] + [Qdrant :6333]
```

## Mood agent

Optional per-user behavior flags (all default-off / safe defaults):

- `MOOD_COACH_PROVIDER=groq` — the coach loop is Groq-only by design. Do not point this at a paid provider.
- `MOOD_COACH_MODEL=llama-3.3-70b-versatile` — Groq model used for coaching.
- `MAX_COACH_TURNS=6` — hard upper bound on assistant replies per session.
- `MOOD_EVENING_CHECKIN_TIME=21:00` — local time (HH:MM) of the check-in.
- `MOOD_EVENING_CHECKIN_TZ=Europe/Kyiv` — timezone for the check-in.

When Groq is unavailable, `/coach` replies "unavailable" and does not fall back to a paid provider.

## Google Calendar setup (one-time)

The orchestrator talks to the Google Calendar v3 REST API directly
(`orchestrator/app/google_calendar_api.py`). There is no calendar MCP server:
each user connects their own Google account through the mobile app, and the
resulting OAuth tokens live per-user in the encrypted vault
(`orchestrator/app/google_calendar.py` refreshes them lazily).

### 1. Create an OAuth Client in Google Cloud Console

1. Visit <https://console.cloud.google.com/>.
2. Create a new project (or reuse an existing one).
3. **APIs & Services → Library**: enable **Google Calendar API**.
4. **APIs & Services → OAuth consent screen**: User type External, app name
   "life-agents", scopes `.../auth/calendar.events` and
   `.../auth/calendar.readonly`. Add your Google account as a test user.
5. **Credentials → Create Credentials → OAuth Client ID**: application type
   **iOS** (this is the mobile client — do not reuse the Supabase Auth Google
   client).

> While the consent screen stays in "Testing" mode, Google expires refresh
> tokens after 7 days. Publish the app to "Production" for a permanent setup.

### 2. Put the client in `.env`

```bash
GOOGLE_CALENDAR_OAUTH_CLIENT_ID=<client-id>.apps.googleusercontent.com
GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET=<secret>
GOOGLE_CALENDAR_OAUTH_REDIRECT_URI=com.googleusercontent.apps.<client-id>:/integrations-callback
```

The redirect URI must match the iOS URL scheme shown on the OAuth client page.

### 3. Connect from the app

Settings → Integrations → Google Calendar. The app calls
`POST /integrations/google_calendar/start`, opens the returned `auth_url`, and
posts the code back to `POST /integrations/google_calendar/callback` (PKCE, with
a signed `state` nonce stored in the `oauth_state` table).

### 4. Verify

```bash
curl -s -H "Authorization: Bearer <jwt>" localhost:8000/agents/calendar/detail | jq .metrics
```

Expected: `events_count` and today's events. An empty result with
`"Reconnect Google Calendar"` in chat means the refresh token was revoked —
reconnect from the app.

### Troubleshooting

- **503 "Google Calendar OAuth is not configured"**: `GOOGLE_CALENDAR_OAUTH_CLIENT_ID`
  is missing from the orchestrator env.
- **"redirect_uri_mismatch"**: the URL scheme in `.env` does not match the OAuth
  client. Copy it verbatim from the Google Cloud Console page.
- **Calendar silently empty in the briefing**: calls have a 2s budget
  (`_CALENDAR_TIMEOUT_SECONDS` in `calendar_context.py`) and degrade to "no
  calendar section" — check orchestrator logs for `calendar list failed`.

## Home Assistant MCP setup (one-time)

The orchestrator reads live state and performs confirm-gated actions on
Home Assistant via HA's native Model Context Protocol Server integration
(available since HA 2025.2). No custom MCP server or Dockerfile — HA itself
hosts the endpoint at `/mcp_server/sse`.

### 1. Install the integration in HA

HA UI → **Settings → Devices & Services → Add Integration** → search
**Model Context Protocol Server** → **Submit**. By default it uses the Assist
pipeline configuration already on your instance.

### 2. Issue a long-lived access token

HA UI → click your avatar (bottom-left) → **Security** → **Long-Lived Access
Tokens** → **Create Token** → name it `life-agents` → copy the token. Paste
into `.env` as `HA_TOKEN=...`. The token is shown once; re-issue if lost.

### 3. Expose entities to Assist

HA UI → **Settings → Voice assistants → Expose**. Only exposed entities are
visible to MCP tools. Start with one sensor for a smoke check — e.g.,
`sensor.temperature_bedroom`. Add more as you use them.

### 4. Restart the orchestrator to pick up the env

```bash
docker compose up -d --force-recreate orchestrator
docker compose logs --tail 50 orchestrator | grep -E "(MCP|Hass)"
```

Expected: `Loaded N MCP tools: [..., GetLiveContext, HassTurnOn, ...]`.
If you see `No MCP servers configured` or the HA tools are missing, verify
`HA_BASE_URL` and `HA_TOKEN` are both set in `.env` and the container was
recreated (not just restarted — `docker compose restart` does not re-read
env_file).

### 5. Smoke test from the host

```bash
source .env
bash scripts/smoke-ha-mcp.sh
```

Step 1 should print `{"message":"API running."}`; step 2 should list the
discovered `Hass*` tools. If step 1 fails with 401, the token is wrong or
expired. If step 2 fails with SSE handshake errors, HA 2025.2+ is required
for the integration — check HA System Information.

### Troubleshooting

- **"0 tools discovered" but step 1 OK**: the integration is installed but
  no entities are exposed. Go to step 3.
- **orchestrator log shows `MCP tool discovery failed`**: typical causes —
  HA is on a different LAN segment from Docker host, or Docker bridge
  network can't reach `homeassistant.local` (on macOS this usually just works).
  Try `docker compose exec orchestrator curl http://homeassistant.local:8123/api/`
  with the Bearer header to confirm reachability.
- **Mutations fire without confirmation**: the safety clause is in
  `_SYSTEM_PROMPT` but LLMs sometimes ignore it on smaller models. If using
  Groq Llama 3.3 70B (recommended), this is rare but possible. File an
  issue and consider a stricter gate.

## Payoneer Finance PDF

**One-time setup:**

1. Apply migration 0006:
   ```bash
   docker compose exec -T postgres psql -U lifeagents -d lifeagents < db/migrations/0006_finance.sql
   ```
2. Rebuild orchestrator after code changes:
   ```bash
   docker compose up -d --build orchestrator
   ```

**Ingest workflow:**

Upload a Payoneer monthly-statement PDF via `POST /finance/upload`.

Orchestrator parses the PDF deterministically via pymupdf text extraction
(5-line groups anchored on the "Date/Description/Amount/Currency/Running
Balance" table header), synthesizes a `txn_id` via
`sha256(period|date|desc|amount|currency|running_balance)`, UPSERTs on
conflict, and LLM-categorizes new rows with a description cache
(`finance_category_cache`).

Chat queries use three ReAct tools:

- `query_finance_summary("2026-04")` — income + spending snapshot
- `query_finance_categories("2026-04")` — breakdown
- `query_finance_runway()` — balance + runway per currency

**Smoke:**

```bash
bash scripts/smoke-finance-pdf.sh
```

The smoke script builds a synthetic Payoneer-shaped PDF at runtime via
pymupdf and POSTs it to `/finance/upload`, so it needs no real statement
file on disk.

## Medication Agent

Peer-agent on port 8008. Records medication/supplement schedules + intake
logs, computes adherence on demand via the `analyze_adherence` skill.

### Commands

- `/med new <free-text>` — e.g. `/med new магний 200мг каждый вечер в 21:00`
- `/med <name> [dose] [note]` — log a dose taken
- `/med list` — active medications
- `/med stop <name>` — archive

Smoke check: `./scripts/smoke-medication.sh` exercises all 5 skills via A2A.

## Observability (Langfuse v3)

The stack includes self-hosted Langfuse v3 for OTEL tracing of every user request across orchestrator, agents, sync_service, and MCP calls.

**UI:** http://localhost:3100

**First-time bootstrap:** Langfuse v3 auto-creates the project + owner user + API keys from `LANGFUSE_INIT_*` env vars on first boot. No manual signup.

**Required env** (in `.env`):

- `LANGFUSE_SALT` — ≥32 char random string
- `LANGFUSE_ENCRYPTION_KEY` — EXACTLY 64 hex chars. Generate: `openssl rand -hex 32`
- `LANGFUSE_NEXTAUTH_SECRET` — ≥32 char random
- `LANGFUSE_POSTGRES_PASSWORD`, `LANGFUSE_CLICKHOUSE_PASSWORD`, `LANGFUSE_REDIS_PASSWORD`, `LANGFUSE_MINIO_PASSWORD`
- `LANGFUSE_INIT_USER_EMAIL`, `LANGFUSE_INIT_USER_PASSWORD`
- `LANGFUSE_PUBLIC_KEY` — e.g. `pk-lf-lifeagents-owner`
- `LANGFUSE_SECRET_KEY` — e.g. `sk-lf-<random>`

**Telemetry consumer env** (applies to orchestrator + all agents + sync-service):

- `TELEMETRY_ENABLED=true`
- `TELEMETRY_CAPTURE_BODIES=full` — options: `full` (default dev), `metadata` (no prompts/completions), `consented` (per-user opt-in via `telemetry_consent` table)
- `LANGFUSE_DEFAULT_USER_ID=owner` — fallback for set_span_user(None)
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://langfuse-web:3000/api/public/otel`

**Smoke:** `bash scripts/smoke-langfuse.sh`

**Full-stack E2E smoke:** `bash scripts/smoke-telemetry-e2e.sh`

**Wipe Langfuse state (dev only):** `bash scripts/wipe-langfuse.sh`

**Consent table:** `telemetry_consent (user_id, bodies_ok, updated_at)`. Only meaningful in `consented` mode. Owner row auto-seeded with `bodies_ok=TRUE` by migration 0007.

**Right-to-erasure:** `DELETE /api/public/traces?userId=<id>` via Langfuse public API. Works because every root span carries `langfuse.user.id`.

**Startup order:** Langfuse services (postgres, clickhouse, redis, minio → worker → web) come up first. Application services do NOT `depends_on` Langfuse — telemetry is graceful-fallback; unreachable Langfuse logs a warning but never blocks the app.

**RAM:** Langfuse stack adds ~2.2 GB overhead (clickhouse ~1GB, web+worker ~768MB, postgres+redis+minio ~450MB).

**Troubleshooting:**

- `langfuse-web` crash-looping with 'Bad encryption key' — `LANGFUSE_ENCRYPTION_KEY` is not exactly 64 hex chars.
- First boot takes 60-90s (clickhouse initial schema migration). If `smoke-langfuse.sh` step 1 times out, extend its `seq 1 60` to `1 90`.
- Traces not appearing: check `docker compose logs langfuse-worker` — worker drains queue; if it's crashed, traces pile up in Redis and never materialize.
- If `ClickHouse unhealthy` on boot (ports 8123 refuse connection): IPv6 binding issue on docker-for-mac. The healthcheck uses `127.0.0.1` explicitly; if you see `localhost:8123` fall-through, re-pull the compose file.

**Consent mode switching (when moving from single-user dev to multi-user):**

1. Set `TELEMETRY_CAPTURE_BODIES=consented` in `.env`.
2. Ensure each user has a row in `telemetry_consent` with their actual `user_id`. Row absent → treated as `bodies_ok=FALSE` (conservative).
3. In `orchestrator`, replace `LANGFUSE_DEFAULT_USER_ID` usage with JWT/session-sourced user_id when adding mobile auth.
4. Redeploy; no code changes required.

Verify: flip `telemetry_consent.bodies_ok` for a user, send a new `/chat/stream`, then check Langfuse trace — prompts should appear (consented=TRUE) or show `[REDACTED]` (consented=FALSE).

## Running the mobile app against the local backend

The mobile app supports three API modes (configured via `apps/mobile/.env.local`):

- `mock` (default in tests): in-memory fixtures, no backend needed.
- `local`: hits `EXPO_PUBLIC_API_BASE_URL` — use your Mac for a real dev loop.
- `cloud`: hits `EXPO_PUBLIC_API_BASE_URL_CLOUD` — populated by P0 deploy.

See `apps/mobile/.env.local.example` and `scripts/mac-ip.sh` for setup. For off-network device testing, Tailscale is the recommended bridge.
