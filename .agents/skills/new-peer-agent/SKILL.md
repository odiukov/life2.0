---
name: new-peer-agent
description: Scaffold a new peer agent (FastAPI + A2A SDK) matching the existing peer agents in the life-agents repo. Use when the user runs /new-peer-agent <name> or asks to create a new domain agent. Generates the 4-file app layout, Dockerfile, requirements, docker-compose entry, and orchestrator wiring.
disable-model-invocation: true
---

# new-peer-agent

Scaffold a new peer agent following the life-agents convention.

## Usage

`/new-peer-agent <name>` where `<name>` is short, lowercase, no spaces (e.g. `finance`, `meditation`, `social`).

If invoked without a name, ask for one before doing anything.

## Reference

The canonical implementation is `agents/mood/`. Read it before generating to pick up small conventions (telemetry init order, `instrument_fastapi_app`, `PostgresTaskStore(agent=...)`, etc.). Do not copy mood-specific domain logic — only the structure.

## Steps

### 1. Discover current state

Never assume a fixed count or port. Run these first:

```bash
# Existing peer agent directories
ls -1 agents/ | grep -v '^__' | grep -v '\.py$'

# All taken host ports in compose
grep -E '^\s+- "[0-9]+:[0-9]+"' docker-compose.yml | sort -u

# Specifically: which 800x ports are taken
grep -oE '"80[0-9]{2}:80[0-9]{2}"' docker-compose.yml | sort -u
```

Pick the lowest free integer in the 8001–8099 range that isn't already mapped. The orchestrator listens on 8000, so never use that.

### 2. Create the app directory

```
agents/<name>/
├── Dockerfile
├── requirements.txt
└── app/
    ├── __init__.py        # empty
    ├── main.py            # FastAPI + A2A entrypoint
    ├── executor.py        # AgentExecutor subclass — skill dispatch
    ├── skills.py          # AgentCard skill list + SKILL_PROMPTS map
    └── prompt.py          # one prompt builder per skill
```

Also: `agents/<name>/__init__.py` (empty) so the package is importable.

### 3. main.py template

```python
"""<Name> agent HTTP entrypoint."""
from shared.telemetry import init_telemetry, instrument_fastapi_app

init_telemetry("agent-<name>")

import logging

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from fastapi import FastAPI

from shared.a2a_store import PostgresTaskStore

from .executor import <Name>AgentExecutor
from .skills import build_agent_card

logger = logging.getLogger(__name__)

app = FastAPI(title="<Name> Agent")
instrument_fastapi_app(app)


@app.get("/health")
async def health():
    return {"status": "ok"}


def _build_a2a_app() -> A2AStarletteApplication:
    handler = DefaultRequestHandler(
        agent_executor=<Name>AgentExecutor(),
        task_store=PostgresTaskStore(agent="<name>"),
    )
    return A2AStarletteApplication(agent_card=build_agent_card(), http_handler=handler)


app.mount("/", _build_a2a_app().build())
```

**Critical**: `init_telemetry()` MUST be the first non-doc statement. Reordering loses module-import spans.

### 4. skills.py template

Mirror `agents/mood/app/skills.py`. Define `SKILLS: list[AgentSkill]` (with stable `id`, descriptive `name`, `description`, `tags`, and 1–3 `examples`), `build_agent_card()` reading from `<NAME>_AGENT_URL` env var with a default `http://agent-<name>:<port>/`, and a `SKILL_PROMPTS: dict[str, PromptFn]` mapping each skill id to its async prompt builder.

The keys of `SKILL_PROMPTS` MUST match `SKILLS[*].id` exactly (the a2a-contract-reviewer subagent enforces this).

### 5. executor.py template

Mirror `agents/mood/app/executor.py`. Reuse the helpers verbatim:

- `_extract_text(ctx)`, `_metadata_skill(ctx)`, `_params_from_metadata(ctx)`, `_infer_skill_via_llm(message)`
- `_emit_status`, `_emit_artifact`, `_error_message`
- `emit_consulted_peers_artifact` from `shared.consulted` if the agent reads peer artifacts

The executor calls `insert_log(user_id, agent="<name>", type_="<domain>", data=..., source=...)` — always pass `agent=` (memory:healthkit_aggregator_agent_column).

### 6. prompt.py

Async prompt builders, one per skill. Pull recent rows from `health_logs` via `shared.db.fetch_*` helpers (add a new `fetch_<domain>_logs` if needed, in `shared/db.py`). Pull relevant memories via `shared.vector.search_memories`. Format a system template with `history`, `memories`, `task`, `params`.

### 7. Dockerfile

```
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY agents/<name>/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /shared
RUN pip install --no-cache-dir -e /shared

COPY agents/<name>/app/ ./app/

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "<port>"]
```

### 8. requirements.txt

Copy `agents/mood/requirements.txt` verbatim — every peer ships the same a2a-sdk / opentelemetry / traceloop versions.

### 9. docker-compose.yml entry

Insert below the **last existing `agent-*` service** (find it: `grep -n '^  agent-' docker-compose.yml | tail -1`). Match the existing block shape: `build`, `environment` (with `<NAME>_AGENT_URL: http://agent-<name>:<port>/` and `LLM_PROVIDER` etc.), `depends_on: [postgres]`, `ports: ["<port>:<port>"]`, `healthcheck`. Then add the agent to the orchestrator's `depends_on:` block AND append its URL to the orchestrator's `AGENT_URLS:` env (comma-separated).

### 10. Smoke script

Add `scripts/smoke-<name>.sh` mirroring `scripts/smoke-mood.sh`: hit `/.well-known/agent.json`, then send a message via the A2A `message/send` JSON-RPC, then assert artifacts.

### 11. Verification

After scaffolding:

- `docker compose up --build agent-<name> -d` starts cleanly, healthcheck passes.
- `curl http://localhost:<port>/.well-known/agent.json` returns the AgentCard with all skill ids.
- The orchestrator picks up the new agent: `docker compose logs orchestrator | grep agent-<name>`.
- `bash scripts/smoke-<name>.sh` passes.

## Things that bite

- **Forgetting `agent=` in `insert_log`** — readers filter by it. Empty `agent` rows are invisible.
- **Telemetry init not first** — module imports happen before tracing starts; you lose those spans silently.
- **Port collision** — pick the next free integer (see step 1 for discovery commands). `lsof -i :<port>` to confirm nothing else on the host is bound.
- **Calendar-mcp restart pairing** — not relevant unless the new agent calls calendar-mcp; if it does, restart orchestrator + calendar-mcp together (memory:ops_docker_and_migrations).
- **Mood-coach Groq lock** — only mood is hard-locked to Groq. Don't replicate that pattern unless the user asks.
