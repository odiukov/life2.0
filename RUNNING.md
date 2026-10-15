# Running Life Agents

## Prerequisites

- Docker Desktop (or OrbStack / Colima) running
- An API key for the provider selected in `LLM__DEFAULT`
- `curl` and `jq` for HTTP checks

## First-time setup

1. Copy `.env.example` to `.env`.
2. Set `APP_OWNER_PASSWORD`, `APP_RW_PASSWORD`, `AUTH_JWT_SECRET`, `SECRETS__KEY`, and a provider API key. Keep the sealing key backed up; changing it makes stored integration credentials unreadable.
3. Choose `LLM__DEFAULT=<provider>:<model>` and optional `LLM__TASKS__*` routes. The mood coach route uses Groq only.
4. For a local demo, set `AUTH_MODE=dev`. Use OAuth mode for a reachable deployment.

Upgrading from before 3c: remove the old legacy-role password and DSN entries from `.env`. Home Assistant credentials now belong to the family connection in the app; remove `HA_TOKEN` and `HA_BASE_URL`, then reconnect in the family panel if the old setup used only those variables.

## Start and verify

```bash
docker compose up --build -d
docker compose ps
```

Wait until `migrate`, orchestrator, sync service and the needed agents are healthy. In local development mode, create and read a task with a fixed demo user:

```bash
USER_ID=de000000-0000-4000-8000-000000000001
curl -fsS -H "X-User-Id: $USER_ID" -H 'Content-Type: application/json' \
  -d '{}' http://localhost:8000/tasks
curl -fsS -H "X-User-Id: $USER_ID" http://localhost:8000/agents
```

The first response contains a task `id`; use `POST /tasks/{id}/messages` with multipart `text` for SSE chat. The mobile app stores the open task ID and restores its transcript from `GET /tasks/{id}` after a restart.

Run `bash scripts/acceptance_orchestrator.sh` for the full stack checks after configuring a real model and an isolated test stack.

## Checkpoints

Alembic creates four checkpoint tables with the schema pinned to `langgraph-checkpoint-postgres` 3.1.3. The orchestrator verifies that version at startup and refuses to run if it differs. Each task has a server-built, tenant-scoped checkpoint key. Closing a task removes its checkpoint and transcript rows together.

## Logs and stop

```bash
docker compose logs -f orchestrator
docker compose down
```

Logs contain codes, names, IDs and counts; request bodies, transcripts, tokens and exception messages are omitted.

## Mood agent

Optional per-user behavior flags (all default-off / safe defaults):

- `MOOD_COACH_PROVIDER=groq` — the coach loop is Groq-only by design. Do not point this at a paid provider.
- `MOOD_COACH_MODEL=llama-3.3-70b-versatile` — Groq model used for coaching.
- `MAX_COACH_TURNS=6` — hard upper bound on assistant replies per session.
- `MOOD_EVENING_CHECKIN_TIME=21:00` — local time (HH:MM) of the check-in.
- `MOOD_EVENING_CHECKIN_TZ=Europe/Kyiv` — timezone for the check-in.

When Groq is unavailable, `/coach` replies "unavailable" and does not fall back to a paid provider.

## Google Calendar setup

Create a dedicated Google OAuth client for Calendar access and set `GOOGLE_CALENDAR_OAUTH_CLIENT_ID` and `GOOGLE_CALENDAR_OAUTH_REDIRECT_URI` in `.env`. Register the redirect URI from the mobile app configuration. Connect from Settings → Integrations → Google Calendar. The gateway signs a one-time PKCE state and sends the returned code to the calendar agent, which stores sealed tokens per user. A revoked refresh token requires reconnecting in the app.

## Home Assistant setup

Install Home Assistant's Model Context Protocol Server integration and expose the intended entities to Assist. Create a long-lived access token in Home Assistant, then connect it from the app's family Home Assistant panel. Any household member can see the connection status; changes proposed by chat require confirmation in the app. The service no longer reads `HA_BASE_URL` or `HA_TOKEN` from `.env`.

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

Attach a Payoneer statement PDF to a task message. The finance agent parses and categorizes transactions and stores them under the authenticated user. The task transcript shows the import summary. `POST /finance/upload` and its smoke script were removed; the chat attachment path is the supported workflow.

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
- `TELEMETRY_CAPTURE_BODIES=consented` — default; `full` is for a private development stack, `metadata` records token counts only
- `LANGFUSE_DEFAULT_USER_ID=owner` — fallback for set_span_user(None)
- `OTEL_EXPORTER_OTLP_ENDPOINT=http://langfuse-web:3000/api/public/otel`

**Smoke:** `bash scripts/smoke-langfuse.sh`

**Full-stack check:** `bash scripts/acceptance_orchestrator.sh`

**Wipe Langfuse state (dev only):** `bash scripts/wipe-langfuse.sh`

**Consent table:** `telemetry_consent (user_id, bodies_ok, updated_at)` uses UUID users. Missing rows deny body capture.

**Right-to-erasure:** `DELETE /api/public/traces?userId=<id>` via Langfuse public API. Works because every root span carries `langfuse.user.id`.

**Startup order:** Langfuse services (postgres, clickhouse, redis, minio → worker → web) come up first. Application services do NOT `depends_on` Langfuse — telemetry is graceful-fallback; unreachable Langfuse logs a warning but never blocks the app.

**RAM:** Langfuse stack adds ~2.2 GB overhead (clickhouse ~1GB, web+worker ~768MB, postgres+redis+minio ~450MB).

**Troubleshooting:**

- `langfuse-web` crash-looping with 'Bad encryption key' — `LANGFUSE_ENCRYPTION_KEY` is not exactly 64 hex chars.
- First boot takes 60-90s (clickhouse initial schema migration). If `smoke-langfuse.sh` step 1 times out, extend its `seq 1 60` to `1 90`.
- Traces not appearing: check `docker compose logs langfuse-worker` — worker drains queue; if it's crashed, traces pile up in Redis and never materialize.
- If `ClickHouse unhealthy` on boot (ports 8123 refuse connection): IPv6 binding issue on docker-for-mac. The healthcheck uses `127.0.0.1` explicitly; if you see `localhost:8123` fall-through, re-pull the compose file.

**Consent:** `TELEMETRY_CAPTURE_BODIES=consented` is the default. Use `make telemetry-consent USER_ID=<uuid>` to enable body capture for one user, or add `OFF=1` to disable it. Send a new task message and check its Langfuse trace; users without consent show redacted bodies.

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
and compares the orchestrator's SSE answer with its persisted task transcript.
If no genuine LLM key is configured, set `ACCEPTANCE_LLM_AVAILABLE=0`; direct kitchen chat,
orchestrator chat is then reported as `SKIP`, while SQL-seeded inventory
still exercises joining, actions, digest and isolation. Skipped acceptance exits nonzero and
must not be reported as a complete pass. Also run `make lint`, `make test`,
`make test-integration`, `pnpm -r typecheck`, and the mobile and UI tests.

### Migrated health-agent acceptance

`make evals` includes the health agents' real-provider evals. A skipped eval is not
an acceptance pass. Regenerate prompt snapshots with `uv run pytest --update-snapshots`
(select the relevant snapshot tests when needed). Review snapshot diffs in every PR
that changes a prompt.

With a configured stack running in `AUTH_MODE=dev`, run `bash scripts/acceptance_agents.sh`. It needs `curl` and `jq`, creates a separate task for each domain agent, checks the agent card and complete SSE response, and prints only agent names and task IDs. Set `API`, `AGENT_HOST` and `ACCEPTANCE_USER_ID` to override defaults. Use an isolated stack with a real model; this script does not assess answer quality.

### Sync privacy and concurrent reconnects

Sync's service, smoke and re-encryption entrypoints sanitize logs at every level,
including vendor DEBUG messages. Diagnostics retain fixed codes and service identifiers;
exception text, credentials, tokens and fetched data are never printed. Re-encryption
failures exit nonzero with `sync_configuration_invalid` or `sync_reencrypt_unavailable`.

If credentials are replaced or disconnected during a fetch, sync discards the obsolete
results and returns `unavailable` without marking success. Token persistence and data
writes each check the locked credential revision. Identical reconnects also invalidate
in-flight work; retry after the normal cooldown.
