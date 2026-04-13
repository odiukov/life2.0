# Running Life Agents

## Prerequisites

- Docker Desktop (or OrbStack / Colima) installed and running
- Claude Code subscription (logged in via `claude` CLI on your host machine)

## First-time Setup

1. Clone or navigate to the project directory
2. Copy environment file:
   ```bash
   cp .env.example .env
   ```
3. Verify Claude auth is available:
   ```bash
   claude --version
   ```

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
[Sleep Agent :8001] → build prompt → claude CLI → store in DB/Qdrant
  ↓
[Postgres :5432] + [Qdrant :6333]
```
