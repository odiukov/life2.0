# A2A v0.2 Compliance + Router Cleanup — Design

**Date:** 2026-04-14
**Status:** Draft
**Scope:** Spec #1 of 4 in the standards-compliance refactor series.

## Motivation

Current agent-to-agent communication is a custom REST protocol ([shared/shared/a2a.py](../../../shared/shared/a2a.py), [agents/sleep/app/main.py](../../../agents/sleep/app/main.py)) that declares `/.well-known/agent.json` but does not conform to the Google A2A specification. External A2A-compatible agents (Google ADK, LangGraph A2A adapter, other ecosystem tools) cannot interoperate.

Additionally, the orchestrator carries a legacy keyword-based intent classifier ([orchestrator/app/router.py](../../../orchestrator/app/router.py)) that duplicates routing responsibility with the LangGraph ReAct agent.

Goal: make agents and orchestrator speak standard **A2A v0.2+** so that any A2A-compliant client can call our agents and we can call third-party A2A agents without glue code. Collapse routing into a single LangGraph-based layer.

## Design decisions (locked)

| # | Decision | Choice |
|---|---|---|
| 1 | A2A SDK | Official `a2a-sdk` (PyPI, Google) |
| 2 | Compliance scope | `message/send` + `message/stream` + `tasks/get` + `tasks/cancel`. No push notifications. |
| 3 | Migration | Big bang — break custom REST, no side-by-side. All in one PR/plan. |
| 4 | Skill routing | `Message.metadata.skillId` with LLM-infer fallback for external callers. |

## Component changes

### Agents (`agents/{sleep,workout,nutrition}`)

- Each agent mounts `A2AStarletteApplication` under its existing FastAPI app: `app.mount("/", a2a_app)`. FastAPI retains `/health` and any future metrics routes.
- SDK auto-provides: `/` (JSON-RPC endpoint implementing `message/send`, `message/stream`, `tasks/get`, `tasks/cancel`) and `/.well-known/agent.json`.
- Per-agent `AgentExecutor` implementation (one class per agent) holds business logic.
- Files deleted: `agents/*/app/a2a.py` types (moved to SDK), `agents/*/app/tasks.py` switch logic (replaced by skill-prompt dict).
- `shared/shared/claude_runner.py` unchanged; invoked from `AgentExecutor.execute()`.

### AgentCard (v0.2 schema)

Each agent publishes a card like:

```json
{
  "protocolVersion": "0.2.5",
  "name": "sleep-agent",
  "description": "Health agent analyzing sleep patterns",
  "url": "http://agent-sleep:8001/",
  "version": "1.0.0",
  "capabilities": { "streaming": true, "pushNotifications": false },
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"],
  "skills": [
    { "id": "log_sleep", "name": "Log Sleep", "description": "...", "tags": ["sleep","logging"] },
    { "id": "analyze_sleep", "name": "Analyze Sleep", "description": "...", "tags": ["sleep","analysis"] },
    { "id": "get_sleep_recommendations", "name": "Sleep Recommendations", "description": "...", "tags": ["sleep","advice"] },
    { "id": "briefing", "name": "Daily Briefing Contribution", "description": "Domain summary for cross-agent briefing", "tags": ["briefing"] }
  ]
}
```

`workout-agent` and `nutrition-agent` follow the same pattern with their respective skill IDs (existing `task_type` values from current `tasks.py` map 1:1 to new `skill.id`).

### Routing inside AgentExecutor

`AgentExecutor.execute(context, event_queue)`:

1. Read `skill_id = context.message.metadata.get("skillId")`.
2. If present, look up a prompt-builder in `SKILL_PROMPTS: dict[str, Callable[[Message], str]]`. The per-skill prompt logic is ported from the existing `tasks.py` switch without changes in behaviour.
3. If absent (external client that doesn't set metadata), fall back to a Claude-call with a system prompt: *"Given the agent capabilities below, determine which skill applies to the user message and execute it."* The agent's own skill list is injected into the prompt.
4. Peer consultation logic from current `_decide_peer_consultation` is preserved but peer calls are routed through `A2AClient` (see Orchestrator section below) instead of raw `httpx`.
5. Streaming response emits A2A events (see Streaming mapping).
6. `AgentExecutor.cancel()` — kills the stored `subprocess.Popen` handle and enqueues `TaskStatusUpdateEvent(state=canceled, final=true)`.

### Orchestrator

- `orchestrator/app/router.py` — **deleted**. Keyword-based `classify_intent` removed.
- `/chat` polling endpoint — **deleted**. Telegram bot already uses `/chat/stream`.
- `/chat/stream` — retained (telegram entry point), but internally reuses the LangGraph graph exposed via `/agui`.
- LangGraph tools in `orchestrator/app/health_agent.py` change from N tools-per-skill to one generic tool per agent:

  ```python
  @tool
  async def ask_sleep_agent(
      message: str,
      skill: Literal["log_sleep", "analyze_sleep", "get_sleep_recommendations"]
  ) -> str:
      """Call sleep agent. Pick skill based on user intent."""
      return await a2a_client_sleep.send_message(
          message=message,
          metadata={"skillId": skill},
      )
  ```

  Analogous `ask_workout_agent`, `ask_nutrition_agent`.
- Agent discovery: `A2ACardResolver.get_agent_card(base_url)` per configured agent URL at startup. Replaces current `registry.py` + `httpx` code.
- Peer-to-peer consultation inside agents (`shared/shared/peer.py`) — refactored to use the same `A2AClient` / `A2ACardResolver` as the orchestrator. Peer cards are resolved lazily on first call and cached.

### Shared

- `shared/shared/a2a.py` — **deleted**. Types come from `a2a.types` (SDK).
- `shared/shared/peer.py` — rewritten to use `A2AClient`.
- `shared/shared/claude_runner.py` — unchanged.

### Telegram bot

Unchanged. Continues to call orchestrator `/chat/stream`.

## Task persistence

A2A `Task` has `id`, `contextId`, `status.state`, `artifacts[]`, `history[]`. The SDK requires a `TaskStore` implementation for `tasks/get` to work across the task lifecycle.

Postgres schema migration on existing `tasks` table:

```sql
ALTER TABLE tasks
  ADD COLUMN task_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
  ADD COLUMN context_id UUID,
  ADD COLUMN state TEXT NOT NULL DEFAULT 'submitted',
  ADD COLUMN skill_id TEXT,
  ADD COLUMN artifacts JSONB,
  ADD COLUMN history JSONB;

ALTER TABLE tasks RENAME COLUMN task_type TO skill_id_legacy;
UPDATE tasks SET skill_id = skill_id_legacy WHERE skill_id IS NULL;
ALTER TABLE tasks DROP COLUMN skill_id_legacy;
```

`input` / `output` columns are kept for briefing and analytics queries that already read them.

State transitions: `submitted` → `working` (on subprocess start) → `completed` / `failed` / `canceled`. Each transition triggers a row update.

`shared/shared/a2a_store.py` (new): `PostgresTaskStore(TaskStore)` implementing `save`, `get`, `delete` on top of `asyncpg`. Wired into `DefaultRequestHandler` per agent, replacing the SDK's `InMemoryTaskStore`.

## Streaming mapping (Claude CLI → A2A events)

Claude CLI runs with `--output-format stream-json`. Each event maps:

| Trigger | A2A event |
|---|---|
| Before subprocess spawn | `TaskStatusUpdateEvent(state=working)` |
| Each text chunk | `TaskArtifactUpdateEvent(artifact={parts:[TextPart(text=chunk)]}, append=true, lastChunk=false)` |
| Subprocess exit 0 | `TaskArtifactUpdateEvent(lastChunk=true)` + `TaskStatusUpdateEvent(state=completed, final=true)` |
| Subprocess exit ≠0 | `TaskStatusUpdateEvent(state=failed, final=true, message=<stderr>)` |
| Cancel invoked | `subprocess.kill()` → `TaskStatusUpdateEvent(state=canceled, final=true)` |

For non-streaming `message/send`, the SDK aggregates artifacts into the final `Task` response automatically.

## Error handling

- `A2AClient` call timeout (default 30 s retained) → SDK raises → orchestrator tool returns `"Agent unavailable: <name>"`. LangGraph decides next step.
- `skillId` not in `SKILL_PROMPTS` and LLM fallback cannot determine intent → Task transitions to `failed` with message `"cannot determine skill"`.
- `PostgresTaskStore.save()` error → Task → `failed`, logged, service continues running (no fatal crash).
- Peer consultation failure (one of `shared/peer.py` callees unavailable) → current behaviour preserved: log warning, continue without peer artifacts.

## Testing

- **Unit** — `AgentExecutor.execute` with mocked Claude runner: verify state transitions, `metadata.skillId` routing, LLM fallback path, cancel path.
- **Integration** — docker-compose up; orchestrator calls sleep-agent via real `A2AClient`; assert response is a valid A2A `Task` with `status.state == completed` and at least one artifact.
- **Spec conformance** — manual smoke:
  - `curl http://agent-sleep:8001/.well-known/agent.json` → validates against v0.2 `AgentCard` schema via SDK.
  - `curl -X POST http://agent-sleep:8001/ -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{...}}'` → valid Task response.
  - `curl -X POST ... "method":"tasks/get" ... ` → returns previously created Task.
  - `curl -X POST ... "method":"tasks/cancel" ... ` → cancels in-flight Task.
- **Regression** — telegram bot e2e: `/sleep как спалось` returns meaningful answer. Daily briefing pipeline ([briefing.py](../../../orchestrator/app/briefing.py)) still produces cross-agent summary.

## Files changed (summary)

**Deleted:**
- `orchestrator/app/router.py`
- `shared/shared/a2a.py`
- `agents/{sleep,workout,nutrition}/app/a2a.py`
- `agents/{sleep,workout,nutrition}/app/tasks.py` switch logic (replaced)

**New:**
- `shared/shared/a2a_store.py` — `PostgresTaskStore`
- `agents/{sleep,workout,nutrition}/app/executor.py` — `AgentExecutor` subclass
- `agents/{sleep,workout,nutrition}/app/skills.py` — `SKILL_PROMPTS` dict
- `db/migrations/0002_a2a_task_schema.sql`

**Modified:**
- `agents/{sleep,workout,nutrition}/app/main.py` — mount A2A app
- `orchestrator/app/main.py` — remove `/chat`, remove router usage
- `orchestrator/app/health_agent.py` — new generic per-agent tools
- `orchestrator/app/registry.py` — use `A2ACardResolver`
- `orchestrator/app/briefing.py` — replace direct `httpx` calls with `A2AClient` (passes `metadata.skillId="briefing"`)
- `shared/shared/peer.py` — use `A2AClient`
- `requirements.txt` files — add `a2a-sdk`

## Out of scope

- Push notifications (`tasks/pushNotificationConfig/*`).
- Multi-turn `contextId` usage beyond storing it — no conversation threading yet.
- Authentication on A2A endpoints — local Docker network for now.
- External A2A agent integration — this spec makes it *possible*, not *used*.
