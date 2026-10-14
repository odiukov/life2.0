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

3. Set `APP_OWNER_PASSWORD`, `APP_RW_PASSWORD` and `APP_LEGACY_PASSWORD` in `.env`
   (letters, digits, `-` and `_`). The migrate service bootstraps roles as the configured
   administrator, then runs Alembic strictly as `app_owner`; services wait for success.
4. All health peers read `LLM__DEFAULT` (`<provider>:<model>`) and optional `LLM__TASKS__*`
   routes instead of `LLM_PROVIDER` / `LLM_MODEL`. Keep both routes aligned for the same
   provider, and supply its API key. Health peers connect using `app_rw`; unmigrated
   services use `app_legacy`. See [database role details](deploy/postgres/README.md).

## LLM provider

Set `LLM_PROVIDER` in `.env` to one of: `anthropic`, `openrouter`, `gemini`,
`groq`, `ollama`. Default is `openrouter` with a free model. Set the
matching API key.

- **OpenRouter / Anthropic / Gemini:** just set the API key. Plain HTTP.
- **Groq:** just set `GROQ_API_KEY`. Free tier is ~30 req/min, ~14 400 req/day across Llama 3.x models — the most generous free option for tool-calling workloads. Get a key at https://console.groq.com/keys.
- **Ollama:** run Ollama on the host; set `OLLAMA_HOST=http://host.docker.internal:11434`.

Switch providers with an env change and `docker compose up -d --force-recreate <service>`.

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
  -c "SELECT agent, skill_id, output, created_at FROM tasks ORDER BY created_at DESC LIMIT 3;"
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

## Garmin and Yazio sync

The `sync-service` pulls each user's Garmin sleep, activities, daily stats, and HRV for the last
7 days, and Yazio diary for the last 2 days. It runs once a day after 09:00 in the user's own
time zone (`users.timezone`). A failed run is retried after an hour. An authentication failure
is retried the next day, to avoid repeated login attempts after a password change. The app's
"Sync now" button and chat tool sync only the asking user, at most once per 10 minutes per service.

### Migration release order

Stop the legacy sync writer before deploying migration `c0006_sync_rekey`. Deploy `c0006` only
with the Task 8 writer cutover to the new `sync-service`; do not run the legacy writer after the
migration. The old writer can recreate legacy time keys and cause duplicate health logs.
Deploy the updated orchestrator and `sync-service` together, then run `make sync-reencrypt`.

### Credentials key (required)

Integration passwords and tokens are sealed with AES-256-GCM. Before the first deployment,
generate the key once in `.env` if `SECRETS__KEY` is absent:

```bash
echo "SECRETS__KEY=$(openssl rand -base64 32)" >> .env
```

Never replace the key after credentials have been sealed. Back up `.env` securely. Without the key,
stored credentials cannot be read and users must
reconnect Garmin and Yazio. The orchestrator and sync service refuse to start without it.
After upgrading from plaintext storage, seal remaining rows:

```bash
make sync-reencrypt
```

The command reports the number resealed and the number of plaintext rows remaining. It exits
with a failure code if any plaintext rows remain.

### Yazio client (optional)

Yazio has no public API; the service uses the mobile app's OAuth client. Set
`SYNC__YAZIO_CLIENT_ID` and `SYNC__YAZIO_CLIENT_SECRET` in `.env` (renamed from
`YAZIO_CLIENT_ID` and `YAZIO_CLIENT_SECRET`). Without them, Yazio reports `disabled`.

### Settings

| Variable | Default | Meaning |
|---|---|---|
| `SYNC__HOUR` | `9` | Local hour after which daily sync runs |
| `SYNC__INTERVAL_MINUTES` | `15` | How often the scheduler looks for due users |
| `SYNC__MANUAL_COOLDOWN_MINUTES` | `10` | Minimum gap between manual syncs per user and service |
| `SYNC__GARMIN_DAYS` / `SYNC__YAZIO_DAYS` | `7` / `2` | Days re-read on every run |

### Smoke test against the real APIs

```bash
make sync-smoke USER_ID=<uuid> DRY_RUN=1  # fetch and count rows, write no rows or sync state
make sync-smoke USER_ID=<uuid>            # real sync for this user, ignoring the cooldown
```

Dry run can re-seal a legacy plaintext credential when it is read. Run `make sync-reencrypt`
first if a strictly read-only credential store is required. Output contains statuses and counts
only. Statuses are `ok`, `partial` (some parts failed and are retried in the next full window),
`auth_failed` (reconnect the integration), `rate_limited`, `unavailable`, `not_connected`, and
`disabled`.

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

## Foundation development checks

Use Python 3.12 through `uv`; host Python is not the test environment.
`make sync`, `make lint`, `make test`, and `make test-integration` are the standard gates.
Integration tests require Docker and fail clearly when it is unavailable. `make evals`
selects real-provider golden cases; missing, blank or test-placeholder keys skip them.
A zero exit with skipped cases does not establish real-model quality.

Only reset volumes belonging to the development stack you intend to erase. A clean-volume
acceptance run uses its own Compose project so other projects and data remain intact.

## Household, kitchen, voice and notifications

The app reaches household, kitchen, voice and notification routes through the orchestrator
gateway. The kitchen agent and STT service are internal to Compose. On the first start, `stt`
downloads the Whisper model (about 1.6 GB for the default model) into the `whisper_models`
volume. `/voice/transcribe` returns 503 until the model finishes loading and `stt` is healthy.
Use `STT__MODEL=tiny` for a lighter local acceptance run; `make test-slow` uses
`STT_TEST_MODEL=tiny`.

The kitchen agent schedules a daily expiry digest. To run it once for the current time:

```bash
docker compose exec -T agent-kitchen python -m kitchen.run_digest
```

The optional `--now 2099-01-01T23:00:00+00:00` argument is for deterministic
acceptance testing. The command prints the number of households whose digest was sent.

Push delivery requires an Apple Developer account and an EAS `projectId` in the mobile
app's `app.json`. After setting those up, set `NOTIFICATIONS__PUSH=expo` and optionally
`NOTIFICATIONS__EXPO_ACCESS_TOKEN` in `.env`, then recreate `agent-kitchen`. The in-app
inbox remains available when push is off.

For a clean-database acceptance run, use a unique disposable Compose project and a local
ignored `.env` with `AUTH_MODE=dev`. Set `STT__MODEL=tiny` in that config if needed. Never
use `docker compose down -v` on a project that contains data you want to keep. The script
checks that household, kitchen and notification tables are empty before proceeding:

```bash
export ACCEPTANCE_COMPOSE_PROJECT=life20accept_$(date +%s)
export ACCEPTANCE_ENV_FILE=.env
docker compose --env-file "$ACCEPTANCE_ENV_FILE" -p "$ACCEPTANCE_COMPOSE_PROJECT" up -d --build
docker compose --env-file "$ACCEPTANCE_ENV_FILE" -p "$ACCEPTANCE_COMPOSE_PROJECT" ps
bash scripts/acceptance_household_kitchen.sh
# Only after checking the project name, remove that disposable project's volumes:
docker compose --env-file "$ACCEPTANCE_ENV_FILE" -p "$ACCEPTANCE_COMPOSE_PROJECT" down -v
```

If an unrelated optional service image cannot be pulled, start only the acceptance
dependencies in the same isolated project: `postgres qdrant`, then `migrate`, then
`agent-kitchen stt orchestrator`, using `up -d --no-deps --build` for each stage.
Check that PostgreSQL, Qdrant, kitchen and STT are healthy and `/health` on the
orchestrator returns 200. This checks the requested flows, but it is not evidence
that the entire production Compose stack is healthy.

The script uses a future UTC digest date and explicit expiring food fixture so the live
scheduler cannot claim the test digest first. It verifies the raw `app_rw` RLS view as user C
and compares the orchestrator's final chat text with its persisted kitchen tool response.
If no genuine LLM key is configured, set `ACCEPTANCE_LLM_AVAILABLE=0`; direct kitchen chat,
orchestrator chat and verbatim relay are then reported as `SKIP`, while SQL-seeded inventory
still exercises joining, actions, digest and isolation. Skipped acceptance exits nonzero and
must not be reported as a complete pass. Also run `make lint`, `make test`,
`make test-integration`, `pnpm -r typecheck`, and the mobile and UI tests.

### Migrated health-agent acceptance

`make evals` includes the health agents' real-provider evals. A skipped eval is not
an acceptance pass. Regenerate prompt snapshots with `uv run pytest --update-snapshots`
(select the relevant snapshot tests when needed). Review snapshot diffs in every PR
that changes a prompt.

With a configured stack running in `AUTH_MODE=dev`, run
`bash scripts/acceptance_agents.sh` from the repository root. It needs `curl`, `jq`,
Docker Compose and database credentials (`APP_RW_PASSWORD`, `POSTGRES_DB`, from `.env`
or the environment). It writes synthetic entries for a dedicated test user, checks
stored row values under RLS and prints analysis answers with fact checks. Review the
printed answers for accuracy beyond those checks, especially recovery and body where
no direct entry is logged. Use `COMPOSE_PROJECT_NAME` for an isolated stack; the script
never removes volumes. API and agent-card host URLs can be overridden via `API` and
`AGENT_HOST`. Existing entries are preserved; run against a fresh isolated database
for a clean acceptance run.

### Sync privacy and concurrent reconnects

Sync's service, smoke and re-encryption entrypoints sanitize logs at every level,
including vendor DEBUG messages. Diagnostics retain fixed codes and service identifiers;
exception text, credentials, tokens and fetched data are never printed. Re-encryption
failures exit nonzero with `sync_configuration_invalid` or `sync_reencrypt_unavailable`.

If credentials are replaced or disconnected during a fetch, sync discards the obsolete
results and returns `unavailable` without marking success. Token persistence and data
writes each check the locked credential revision. Identical reconnects also invalidate
in-flight work; retry after the normal cooldown.
