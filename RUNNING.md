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
