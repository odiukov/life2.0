# LLM Provider Wrapper — Design

**Date:** 2026-04-14
**Status:** Approved (brainstorm)

## Problem

`orchestrator/app/health_agent.py` builds a `ChatAnthropic` client with a Claude Code OAuth token. The subscription account is hitting `rate_limit_error` (HTTP 429) during normal use, breaking the AG-UI stream in the frontend (`INCOMPLETE_STREAM`). Sub-agents (sleep/workout/nutrition) use the `claude` CLI and are unaffected.

We want a drop-in switch to route the LangGraph health agent through OpenRouter (starting with `openrouter/elephant-alpha`) while keeping Anthropic as the default.

## Goals

- Single switch (`LLM_PROVIDER` env var) selects the provider at startup.
- No auto-fallback. One provider per process, predictable behavior, easy to debug.
- Keep existing Anthropic OAuth token handling intact.
- Isolate provider selection in its own module; `health_agent.py` does not care who serves the model.

## Non-goals

- Changing sub-agents (they use the Claude CLI, no 429 issues).
- Retry/fallback logic across providers.
- Runtime provider switching without restart.

## Scope

| Component | Change |
|---|---|
| `orchestrator/app/llm.py` | **New.** Provider factory. |
| `orchestrator/app/health_agent.py` | Replace local `_build_llm()` with `from .llm import build_llm`. |
| `orchestrator/requirements.txt` | Add `langchain-openai>=0.3`. |
| `.env.example` | Document `LLM_PROVIDER`, `LLM_MODEL`, `OPENROUTER_API_KEY`. |
| `docker-compose.yml` | No change (orchestrator already `env_file: .env`). |

## Design

### Module: `orchestrator/app/llm.py`

Single public function:

```python
def build_llm() -> BaseChatModel: ...
```

Reads env at call time:

- `LLM_PROVIDER` — `anthropic` (default) or `openrouter`.
- `LLM_MODEL` — optional override. Defaults:
  - `anthropic` → `claude-sonnet-4-6`
  - `openrouter` → `openrouter/elephant-alpha`
- Provider-specific key: `ANTHROPIC_API_KEY` or `OPENROUTER_API_KEY`.

#### Anthropic branch

Preserves current OAuth token behavior: if `ANTHROPIC_API_KEY` starts with `sk-ant-oat`, inject a manually constructed `anthropic.AsyncAnthropic`/`anthropic.Anthropic` client into `ChatAnthropic.__dict__` so the token is sent as `Authorization: Bearer` with header `anthropic-beta: oauth-2025-04-20`.

#### OpenRouter branch

```python
return ChatOpenAI(
    model=model,
    temperature=0,
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
)
```

OpenRouter is OpenAI-compatible and relays tool calls for models that support them.

### Error handling

- Unknown `LLM_PROVIDER` → `ValueError` at startup (fail-fast).
- Missing required key for selected provider → `KeyError` from `os.environ[...]` at startup.
- We do NOT validate model availability — surfaced by the first request.

### `.env.example` additions

```
# LLM provider for health agent: anthropic (default) | openrouter
LLM_PROVIDER=anthropic
# Optional model override (defaults: claude-sonnet-4-6 / openrouter/elephant-alpha)
# LLM_MODEL=
# Required when LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=
```

## Testing

Manual:

1. `LLM_PROVIDER=openrouter` in `.env`, set `OPENROUTER_API_KEY`.
2. `docker compose up -d orchestrator` (rebuild for new requirement).
3. Send a health question via the frontend. Verify:
   - No `INCOMPLETE_STREAM` in CopilotKit runtime logs.
   - Sub-agent tool call executes (check `analyze_sleep` etc. reach sub-agent).
   - Final answer renders in UI.
4. Flip `LLM_PROVIDER=anthropic`, restart, confirm legacy path still works.

## Risks

- **Tool-calling compatibility of `elephant-alpha`** — not every OpenRouter model supports function calling reliably. If broken, swap via `LLM_MODEL` to another OpenRouter model that does (e.g. `deepseek/deepseek-chat-v3.1:free`).
- **OpenRouter latency/availability** — free tier may be slow or rate-limited. Acceptable for a stop-gap; not a production posture.
