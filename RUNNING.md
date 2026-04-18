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
{"agents": ["sleep"]}
```

Expected response from /chat:
```json
{"status": "completed", "output": "...Claude's response..."}
```

## Verify Data Was Logged

```bash
docker compose exec postgres psql -U lifeagents -d lifeagents \
  -c "SELECT agent, task_type, output, created_at FROM tasks ORDER BY created_at DESC LIMIT 3;"
```

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
[You] → curl/Telegram/Browser
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
- `MOOD_EVENING_CHECKIN=true|false` — if true, send one Telegram prompt per day at the configured time.
- `MOOD_EVENING_CHECKIN_TIME=21:00` — local time (HH:MM) of the check-in.
- `MOOD_EVENING_CHECKIN_TZ=Europe/Kyiv` — timezone for the check-in.

Coach sessions are ephemeral in-memory state in `telegram_bot` — restarting the bot clears active sessions. When Groq is unavailable, `/coach` replies "unavailable" and does not fall back to a paid provider.

## Google Calendar setup (one-time)

The stack reads Google Calendar via a local wrapper around
`nspady/google-calendar-mcp v2.6.1` (see `./calendar-mcp/Dockerfile` — it clones
that tag and applies a two-line patch in `patches.js` to enable stateful
sessions + JSON responses). OAuth lives entirely inside that container — no
credentials table in Postgres, no OAuth code in our repo.

> The patch is required because upstream v2.6.1 runs the HTTP transport in
> stateless mode, which in MCP TS SDK 1.27 returns 500 on the second request
> of a session — incompatible with `langchain-mcp-adapters`. If you ever bump
> the pinned tag, re-validate that `patches.js` still applies cleanly.

### 1. Create an OAuth Client in Google Cloud Console

1. Visit <https://console.cloud.google.com/>.
2. Create a new project (or reuse an existing one).
3. Navigate to **APIs & Services → Library**, enable **Google Calendar API**.
4. **APIs & Services → OAuth consent screen**: configure app (User type: External; app name "life-agents"; scopes: `.../auth/calendar`). On the Testing tab, add your own Google account as a test user.
5. **APIs & Services → Credentials → Create Credentials → OAuth Client ID**:
   - Application type: **Desktop app**
   - Name: whatever you like (e.g. `life-agents-local`)
   - After creation, click **Download JSON** and save the file to the repo root as `./gcp-oauth.keys.json`.

> **Important:** While your OAuth consent screen stays in "Testing" mode, Google
> auto-expires refresh tokens after 7 days. For a permanent local setup, publish the
> app to "Production" from the OAuth consent screen page. Publishing a Desktop-app
> client does not require Google verification.

### 2. Boot the MCP server alone

```bash
docker compose up -d calendar-mcp
docker compose logs --tail 30 calendar-mcp
```

Expected: container builds (first boot takes 60–90 seconds — it clones and builds
from the pinned git tag). Then it starts and waits for the first auth.

### 3. Run the one-time auth flow

```bash
docker compose exec calendar-mcp npm run auth
```

The command prints a Google consent URL. Open it in any browser on any device,
pick the Google account you added as a test user in step 1, grant consent.
The flow completes automatically (the server captures the redirect).

### 4. Verify the token persisted

```bash
ls -la mcp-config/calendar-mcp/
```

Expected: at least one `*.json` file (token cache) with non-zero size.

### 5. Verify the server survives restart

```bash
docker compose restart calendar-mcp
sleep 10
docker compose logs --tail 30 calendar-mcp | grep -iE "auth|token|ready|listen"
```

Expected: logs show the server coming up, using the persisted token — **no**
"re-auth required" or "token expired" message.

### 6. Boot the rest of the stack

```bash
docker compose up -d
```

The orchestrator loads MCP tools from `calendar-mcp` at startup. Check it worked:

```bash
docker compose logs --tail 50 orchestrator | grep -iE "mcp|calendar"
```

Expected: a line like `Loaded N MCP tools: ['list-events', 'create-event', ...]`.

If the line shows `No MCP servers configured` or `MCP tool discovery failed`, the
server-to-orchestrator wiring has a problem — check `MCP_GOOGLE_CALENDAR_URL` in
`.env`.

### Restart order (important)

The orchestrator opens one long-lived MCP session at startup and keeps it open
for the process lifetime (see `orchestrator/app/mcp_tools.py`). The calendar
server accepts only one session per process, so if you restart the orchestrator
while `calendar-mcp` stays up, the new session's init is rejected and calendar
tool calls hang.

**Always recreate both together when touching the orchestrator:**

```bash
docker compose up -d --force-recreate calendar-mcp orchestrator
```

Restarting the full stack (`docker compose up -d`) is always safe — the
`depends_on: service_healthy` ordering handles boot sequencing.

### Troubleshooting

- **"gcp-oauth.keys.json: no such file"** in `calendar-mcp` logs: you skipped step 1
  or placed the file in the wrong location. The file must be at repo root, next to
  `docker-compose.yml`.
- **"redirect_uri_mismatch"** during `npm run auth`: your OAuth Client type is wrong.
  Recreate as **Desktop app** (not Web app).
- **Token expires after 7 days**: publish the OAuth consent screen to Production mode
  (see step 1 note).
- **Orchestrator doesn't see calendar tools**: check `docker compose logs orchestrator`
  for `MCP tool discovery failed`. If the MCP server is healthy but the URL env is
  missing, verify `MCP_GOOGLE_CALENDAR_URL=http://calendar-mcp:3000` is in `.env`.
