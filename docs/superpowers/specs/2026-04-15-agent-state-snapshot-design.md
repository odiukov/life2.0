# Agent state snapshots via CopilotKit CoAgents (AG-UI StateSnapshot/Delta)

**Date:** 2026-04-15
**Status:** Draft, pending user review
**Scope:** Frontend `useCoAgent` + backend state-snapshot streaming (Plan 4a of standards-compliance series). Replaces nothing of the polling dashboards — only adds live process-state to the chat UI.

## Problem

The chat UI (`CopilotChat`) currently shows a generic spinner while the LangGraph ReAct agent makes A2A calls to sub-agents (3–5s each). The user has no visibility into which sub-agent is being queried, nor immediate confirmation when a log action (`log_meal`, `log_workout`, `log_sleep`) succeeded. Polling the dashboards for confirmation is indirect and delayed.

AG-UI defines `StateSnapshot`/`StateDelta` events (JSON Patch, RFC 6902) for streaming agent-owned state. CopilotKit React exposes `useCoAgent<T>({name})` to subscribe to that state on the frontend. The Python SDK (`copilotkit`) and `ag_ui_langgraph` wire LangGraph state into these events automatically. We are not using any of this today.

## Non-goals

- Dashboards (`/stats`, `/agents`, `/health-summary`) are query results, not agent state. They stay on HTTP polling. A separate future plan may move them to SSE push.
- Durable state across orchestrator restarts. We keep `MemorySaver`. A follow-up plan will migrate to `PostgresSaver` (`langgraph-checkpoint-postgres`).
- Removing `/chat/stream` endpoint — it is used by `telegram_bot/app/client.py` and must stay. Telegram bot does not participate in CoAgent state (it's chat-UI only).

## Standards alignment

Canonical pattern per CopilotKit CoAgents + LangGraph docs:
1. Extend `state_schema` via `TypedDict` with custom keys alongside `messages`.
2. Inside long-running tools, call `copilotkit_emit_state(config, state)` for mid-execution updates (fixes staleness during A2A calls).
3. Tools return `Command(update={...})` for final state changes.
4. Keep `create_react_agent` (prebuilt ReAct).
5. Frontend subscribes via `useCoAgent<T>({name: "default"})` — name matches `LangGraphAgent(name="default")` in orchestrator.

Verified SDK helpers exist at `copilotkit==0.1.39`: `copilotkit_emit_state`, `copilotkit_customize_config`, `copilotkit_emit_tool_call`, `copilotkit_emit_message`, `copilotkit_exit`.

## Architecture

```
Frontend useCoAgent<HealthAgentState>("default")
   ↕ StateSnapshot / StateDelta (AG-UI)
copilotkit-runtime  (Node, @copilotkit/runtime)
   ↕ /agui  (ag_ui_langgraph.add_langgraph_fastapi_endpoint)
orchestrator FastAPI
   ↕ LangGraph stream (MemorySaver checkpointer, thread_id = CopilotKit threadId)
create_react_agent(state_schema=HealthAgentState, tools=[...])
   │
   └─ tool body (e.g. ask_workout_agent):
        1. copilotkit_emit_state(config, {..., currentStep, activeAgent, toolCalls[running]})
        2. await _call_agent_with_artifact(...)  → (text, log_entry | None)
        3. return Command(update={toolCalls[done], lastLoggedEntry?, messages:[ToolMessage]})
```

## State schema

New module `orchestrator/app/state.py`:

```python
from typing import Annotated, Literal, TypedDict, NotRequired
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

ToolStatus = Literal["running", "done", "error"]

class ToolCall(TypedDict):
    id: str
    name: str
    skill: NotRequired[str]
    status: ToolStatus
    startedAt: str
    endedAt: NotRequired[str]
    error: NotRequired[str]

class LogEntry(TypedDict):
    agent: Literal["sleep", "workout", "nutrition"]
    skill: str
    summary: str
    timestamp: str

class HealthAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    currentStep: NotRequired[str]            # "idle" | "querying <agent> (<skill>)" | "composing"
    activeAgent: NotRequired[str | None]
    toolCalls: NotRequired[list[ToolCall]]
    lastLoggedEntry: NotRequired[LogEntry | None]
```

All non-`messages` keys are `NotRequired` — frontend treats absence as "nothing happened yet". No init node needed.

Keys are camelCase to match JS conventions consumed by `useCoAgent<HealthAgentState>`.

## Tool lifecycle (per A2A tool)

Each of `ask_sleep_agent`, `ask_workout_agent`, `ask_nutrition_agent` is refactored to:

1. Accept `config: RunnableConfig`, `tool_call_id: Annotated[str, InjectedToolCallId]`, `state: Annotated[HealthAgentState, InjectedState]`.
2. Build a `ToolCall` entry with `status="running"`, `startedAt=now_iso()`.
3. Call `await copilotkit_emit_state(config, {**state, currentStep, activeAgent, toolCalls: prev + [running_call]})`.
4. Call `_call_agent_with_artifact(agent, message, skill) → (text, log_entry | None)`.
5. On success, return `Command(update={currentStep: "composing", activeAgent: None, toolCalls: updated_with_done, messages: [ToolMessage(text)], lastLoggedEntry: parsed_if_log_skill})`.
6. On exception, return `Command(update={toolCalls: updated_with_error, messages: [ToolMessage(f"Error: ...")]})`.

`sync_health_data` and `send_daily_briefing` tools get the same treatment with `activeAgent="system"`, no `lastLoggedEntry`.

### `toolCalls` trim

In a new `pre_model_hook` (or inside the tool, simpler): cap `toolCalls` at the last 20 entries to keep `StateSnapshot` bounded over long threads.

## Sub-agent changes: `log_entry` artifact

Currently each A2A `Task` returned by sub-agents carries a single text artifact. To avoid brittle LLM/regex parsing in the orchestrator, sub-agents emit a second named artifact for log skills.

**Modified:** `agents/{sleep,workout,nutrition}/app/executor.py` — after a successful `log_*` skill, build:

```python
Artifact(
    artifact_id=str(uuid4()),
    name="log_entry",
    parts=[Part(root=DataPart(data={"summary": "...", "timestamp": "..."}))],
)
```

appended to the existing text artifact. Non-log skills emit only the text artifact (unchanged).

**Orchestrator:** `_call_agent` becomes `_call_agent_with_artifact`. Iterates `task.artifacts`:
- Text from the first text-bearing artifact (unchanged behavior).
- `log_entry` dict from the artifact with `name == "log_entry"`, if present.

Returns `(text, log_entry | None)`.

## Frontend

**New types** in `agui-frontend/src/types.ts`: `ToolCall`, `LogEntry`, `HealthAgentState`.

**New components:**
- `agui-frontend/src/components/AgentStatusBar.tsx` (~40 lines): receives `currentStep`, `activeAgent`, `toolCalls`. Renders a compact bar above the chat input when any running tool exists or `currentStep !== "idle"`. Returns `null` otherwise.
- `agui-frontend/src/components/LastLoggedCard.tsx` (~30 lines): receives `lastLoggedEntry`. Renders a 5s auto-dismiss toast card over the chat area when entry timestamp is within last 30s. Otherwise `null`.

**Hookup:** `agui-frontend/src/pages/DashboardPage.tsx` adds:

```tsx
const { state } = useCoAgent<HealthAgentState>({ name: "default" });
```

and mounts `<LastLoggedCard entry={state?.lastLoggedEntry} />` and `<AgentStatusBar ... />` adjacent to `<CopilotChat />`.

No changes to `copilotkit-runtime/` — `ag_ui_langgraph` emits StateSnapshot/StateDelta automatically; the runtime forwards them by default.

## Data flow — worked example

User: "залогай 30 минут бега"

1. LLM tool call: `ask_workout_agent(message="30 min run", skill="log_workout")`.
2. Tool: `emit_state({currentStep: "querying workout (log_workout)", activeAgent: "workout", toolCalls: [running]})` → frontend `useCoAgent` state updates within ~100ms.
3. Frontend renders `<AgentStatusBar>` with "🔄 querying workout (log_workout)".
4. A2A call to workout-agent (3–5s). Workout-agent handler logs to Postgres, returns Task with text artifact "Logged: 30 min run, ~300 kcal" + `log_entry` artifact `{summary: "30 min run", timestamp: "..."}`.
5. Tool returns `Command(update={currentStep: "composing", activeAgent: None, toolCalls: [done], messages: [ToolMessage], lastLoggedEntry: {agent: "workout", skill: "log_workout", summary: "30 min run", timestamp: "..."}})`.
6. Frontend: `AgentStatusBar` hides, `LastLoggedCard` toast appears for 5s with "✅ 30 min run".
7. LLM composes final reply, streams as text. `RunFinished` event ends the turn.

## Error handling

- A2A call raises → tool catches, returns `Command` with `toolCalls[i].status="error"`, `error=str(e)`, and a `ToolMessage` conveying the error so LLM can respond naturally.
- `copilotkit_emit_state` failure is non-fatal — the tool continues. (We do not wrap it in try/except initially; if logs show failures in prod, add a best-effort wrapper.)
- `log_entry` artifact malformed / missing → `lastLoggedEntry` not set; log a warning. User still sees the text confirmation in the chat message.

## Testing

Backend:
- `tests/orchestrator/test_health_agent_state.py` — per tool, mock `_call_agent_with_artifact` and `copilotkit_emit_state`; assert emit call args and `Command.update` contents for both `log_*` and non-log skills.
- `tests/orchestrator/test_artifact_extraction.py` — `_call_agent_with_artifact` parses text + `log_entry` from synthetic `Task.artifacts`.
- `tests/agents/test_{sleep,workout,nutrition}_executor_log_artifact.py` — executor emits `log_entry` artifact for log skills only.

Frontend:
- `AgentStatusBar.test.tsx` — render matrix: no state, running, done-only, error.
- `LastLoggedCard.test.tsx` — render with/without entry, relative-time, auto-dismiss.
- `DashboardPage.integration.test.tsx` — MSW mocks `/copilotkit` runtime, feeds AG-UI event sequence (RunStarted → StateDelta... → RunFinished); assert both components react.

Manual smoke (in implementation plan):
- `docker compose up`; send "залогай 30 минут бега" in UI.
- Verify statusbar appears with "querying workout (log_workout)", disappears after tool done, toast card shows briefly.

## Known limitations

- `MemorySaver` is in-memory. `lastLoggedEntry` and `toolCalls` do not survive orchestrator restart. Follow-up plan: migrate to `PostgresSaver`.
- `toolCalls` grows per turn; trimmed to last 20 to bound StateSnapshot size.
- Telegram bot does not participate — it uses `/chat`, not `/agui`. CoAgent state is chat-UI only.

## File map

New:
- `orchestrator/app/state.py`
- `agui-frontend/src/components/AgentStatusBar.tsx` (+ `.test.tsx`)
- `agui-frontend/src/components/LastLoggedCard.tsx` (+ `.test.tsx`)
- `tests/orchestrator/test_health_agent_state.py`
- `tests/orchestrator/test_artifact_extraction.py`
- `tests/agents/test_{sleep,workout,nutrition}_executor_log_artifact.py`

Modified:
- `orchestrator/app/health_agent.py` — tools refactored, `_call_agent` → `_call_agent_with_artifact`, `create_react_agent(state_schema=HealthAgentState)`.
- `orchestrator/requirements.txt` — add `copilotkit>=0.1.39`.
- `agents/{sleep,workout,nutrition}/app/executor.py` — emit second `log_entry` artifact for `log_*` skills.
- `agui-frontend/src/types.ts` — add `ToolCall`, `LogEntry`, `HealthAgentState`.
- `agui-frontend/src/pages/DashboardPage.tsx` — wire `useCoAgent`, mount new components.

## Open questions (deferred)

- Should `lastLoggedEntry` clear after 5s on backend side too, or stay in state indefinitely until next log? Current design: stays in state (toast-dismiss is a UI-only concern). User can always see last-logged by opening the thread.
- Do we want `copilotkit_exit` at end of run to signal "run done"? Default behavior already handles this via `RunFinished`. Not adding explicitly.
