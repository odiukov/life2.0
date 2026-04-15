# LLM Provider Wrapper v2 — Design

**Date:** 2026-04-15
**Status:** Approved (brainstorm)
**Supersedes:** `2026-04-14-llm-provider-wrapper-design.md` (orchestrator-only; this v2 extends to all agents and adds more providers)

## Problem

Two pain points in the current LLM setup:

1. **Sub-agents depend on the Claude CLI subprocess + macOS Keychain OAuth token.** Token expires every ~8h and requires manual `scripts/export-auth.sh` before every `docker compose up`. The CLI subprocess is also a bespoke implementation — not a standard interface — so swapping in any other provider requires rewriting the sub-agent call site.
2. **The existing wrapper (`orchestrator/app/llm.py`) only covers the orchestrator.** Sub-agents have no abstraction and hard-code `shared/shared/claude_runner.py`.

We want one standard LLM abstraction across the whole stack, with pluggable providers, so:

- A new provider can be added by writing a `BaseChatModel` subclass (or using an existing LangChain integration) — no forks, no custom protocols.
- Switching providers is a single env-var change, no code changes.
- The project is product-ready: someone cloning the repo sets their preferred provider + API key, runs `docker compose up`, and it works.

## Goals

- Single shared module (`shared/shared/llm.py`) exposes one function `build_llm() -> BaseChatModel`.
- Five providers supported out of the box: `anthropic`, `openrouter`, `gemini`, `ollama`, `claude-cli`.
- Default provider is `openrouter` with a free model, so a fresh clone runs with one free API key.
- Claude CLI stays as a selectable provider via a `ChatClaudeCLI` adapter that implements the `BaseChatModel` contract.
- Drop the bespoke `shared/shared/claude_runner.py` — all its logic moves inside `ChatClaudeCLI`.
- Orchestrator's local `orchestrator/app/llm.py` is removed; orchestrator imports from `shared.llm`.
- LangChain `BaseChatModel` is the public extension point — third parties write a subclass to plug in their provider, as documented by LangChain itself.

## Non-goals

- Runtime provider switching without restart.
- Auto-fallback between providers on failure.
- Per-agent provider overrides (`SLEEP_LLM_PROVIDER` etc.) — global env only. Keeps config simple; can be added later if demand appears.
- A public provider registry inside our module. LangChain's existing class system is the extension point; we don't need a second one.
- Streaming or tool-calling support in `ChatClaudeCLI` (documented limitation).
- Structured-output support in `ChatClaudeCLI`.

## Scope

| Component | Change |
|---|---|
| `shared/shared/llm.py` | **New.** `build_llm()` factory, reads env, returns configured `BaseChatModel`. |
| `shared/shared/chat_claude_cli.py` | **New.** Custom `ChatClaudeCLI(BaseChatModel)` adapter. |
| `shared/shared/claude_runner.py` | **Deleted.** Logic absorbed into `ChatClaudeCLI`. |
| `orchestrator/app/llm.py` | **Deleted.** Orchestrator imports `from shared.llm import build_llm`. |
| `orchestrator/app/health_agent.py` | Import path change only. |
| `agents/sleep/app/executor.py` | Replace `claude_runner.run(...)` call site with `build_llm().ainvoke([SystemMessage, HumanMessage])`. |
| `agents/workout/app/executor.py` | Same as sleep. |
| `agents/nutrition/app/executor.py` | Same as sleep. |
| `shared/requirements.txt` | Add `langchain-anthropic`, `langchain-openai`, `langchain-google-genai`, `langchain-ollama`, `langchain-core`. |
| `orchestrator/requirements.txt` | Reference shared; no duplicate LC packages. |
| Agent `requirements.txt` × 3 | Add/ensure LC deps are pulled in (via shared). |
| `.env.example` | Document all five providers and their keys; default = `openrouter`. |
| `docker-compose.yml` | Ensure `LLM_PROVIDER`, `LLM_MODEL`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_HOST` pass through via `env_file`. |
| `RUNNING.md` | Update: `export-auth.sh` is now optional, only needed when `LLM_PROVIDER=claude-cli`. |
| `tests/test_llm.py` | **New.** Unit tests for every branch of `build_llm()`. |
| `tests/test_chat_claude_cli.py` | **New.** Unit tests for `ChatClaudeCLI` subprocess behavior (mocked). |
| `scripts/smoke-llm.sh` | **New.** Minimal ping→pong round-trip against configured provider. |

## Design

### Module: `shared/shared/llm.py`

Single public function:

```python
from langchain_core.language_models import BaseChatModel

def build_llm() -> BaseChatModel: ...
```

Reads env in this order:

1. `LLM_PROVIDER` — one of `anthropic`, `openrouter`, `gemini`, `ollama`, `claude-cli`. Default: `openrouter`.
2. `LLM_MODEL` — optional. Each provider has a default model if unset.
3. Provider-specific key: `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_HOST`. `claude-cli` reads the OAuth token from `ANTHROPIC_API_KEY` (populated by `scripts/export-auth.sh`).

Unknown `LLM_PROVIDER` → `ValueError("unknown provider: X")`.
Missing required API key → `ValueError("{PROVIDER}_API_KEY not set")`.

### Provider branches

| `LLM_PROVIDER` | Class | Package | Key env | Default `LLM_MODEL` |
|---|---|---|---|---|
| `anthropic` | `ChatAnthropic` | `langchain-anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` |
| `openrouter` | `ChatOpenAI` with `base_url="https://openrouter.ai/api/v1"` | `langchain-openai` | `OPENROUTER_API_KEY` | `meta-llama/llama-3.3-70b-instruct:free` |
| `gemini` | `ChatGoogleGenerativeAI` | `langchain-google-genai` | `GEMINI_API_KEY` | `gemini-2.0-flash-exp` |
| `ollama` | `ChatOllama` | `langchain-ollama` | `OLLAMA_HOST` (optional; defaults to `http://localhost:11434`) | `llama3.1:8b` |
| `claude-cli` | `ChatClaudeCLI` (in-repo) | — | `ANTHROPIC_API_KEY` (OAuth from Keychain) | `claude-sonnet-4-6` |

Each branch is ~10 lines. File stays under ~150 lines.

### Module: `shared/shared/chat_claude_cli.py`

Custom `ChatClaudeCLI(BaseChatModel)`:

```python
class ChatClaudeCLI(BaseChatModel):
    model: str = "claude-sonnet-4-6"
    timeout_seconds: int = 120

    @property
    def _llm_type(self) -> str:
        return "claude-cli"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.model}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        # Sync wrapper around _agenerate via asyncio.run.
        ...

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        # 1. Split messages: system → --system-prompt, rest → concatenated stdin.
        # 2. Require ANTHROPIC_API_KEY in env (OAuth token).
        # 3. Spawn: claude --print --bare --model {self.model}
        #    [--system-prompt "{system_text}"] with that env.
        # 4. Write user/assistant messages to stdin; await stdout with timeout.
        # 5. Return ChatResult(generations=[ChatGeneration(message=AIMessage(content=stdout))]).
        ...
```

**Documented limitations** in class docstring:
- No streaming (`--print` emits the full reply at once).
- No tool calling.
- No structured output.
- OAuth token expires ~8h; caller must re-run `scripts/export-auth.sh`.

Error paths: subprocess non-zero exit → raise `RuntimeError(stderr)`. Timeout → raise `TimeoutError`.

### Migration pattern for sub-agents

Before (sleep/workout/nutrition executor):

```python
from shared.claude_runner import run as claude_run
result = await claude_run(prompt)
```

After:

```python
from shared.llm import build_llm
from langchain_core.messages import SystemMessage, HumanMessage

_llm = build_llm()  # module-scoped, built once

async def run_skill(prompt: str, system: str) -> str:
    result = await _llm.ainvoke([SystemMessage(system), HumanMessage(prompt)])
    return result.content
```

Orchestrator: the existing `build_llm()` call site in `health_agent.py` stays; only the import changes from `.llm` to `shared.llm`.

### Env config

`.env.example`:

```bash
# LLM provider selection. Options: anthropic | openrouter | gemini | ollama | claude-cli
LLM_PROVIDER=openrouter
LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free

# One of these must be set, matching LLM_PROVIDER:
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=
GEMINI_API_KEY=
# OLLAMA_HOST=http://localhost:11434  # only for ollama

# claude-cli: ANTHROPIC_API_KEY is populated by scripts/export-auth.sh
```

### Docker Compose

All four LLM-using services (`agent-sleep`, `agent-workout`, `agent-nutrition`, `orchestrator`) already use `env_file: .env`. No per-service overrides — one env applies to all.

Ollama note: if `LLM_PROVIDER=ollama` and the user runs Ollama on the host, `OLLAMA_HOST` must be `http://host.docker.internal:11434` (documented in `.env.example`).

## Testing

### `tests/test_llm.py`

1. `test_default_provider_is_openrouter` — no env set → `ChatOpenAI` with correct `base_url`.
2. `test_anthropic_branch` — `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` → `ChatAnthropic`, default model `claude-sonnet-4-6`.
3. `test_openrouter_branch` — explicit openrouter env → `ChatOpenAI`, base URL check, default model is the free Llama.
4. `test_gemini_branch` — correct class + default model.
5. `test_ollama_branch` — correct class, default host, default model.
6. `test_claude_cli_branch` — returns `ChatClaudeCLI` instance with the correct default model.
7. `test_llm_model_override` — `LLM_MODEL=custom/x` overrides default for every provider.
8. `test_unknown_provider_raises` — `LLM_PROVIDER=bogus` → `ValueError`.
9. `test_missing_api_key_raises` — for each provider that requires a key, missing key → `ValueError`.

Pure unit tests; no network; no subprocess. `monkeypatch` on env.

### `tests/test_chat_claude_cli.py`

1. `test_agenerate_spawns_expected_cmd` — mock `asyncio.create_subprocess_exec`, assert cmd = `claude --print --bare --model X`, stdin received concatenated user message text, env contains `ANTHROPIC_API_KEY`.
2. `test_system_prompt_goes_via_flag` — if messages include `SystemMessage`, its content goes via `--system-prompt`, not into stdin.
3. `test_subprocess_error_propagates` — non-zero exit → `RuntimeError` with stderr text.
4. `test_subprocess_timeout` — exceeds `timeout_seconds` → `TimeoutError`.
5. `test_missing_token_raises` — no `ANTHROPIC_API_KEY` in env → clear `ValueError`.
6. `test_returns_chatresult` — happy path returns `ChatResult` with one `AIMessage`.

### `scripts/smoke-llm.sh`

Shell script. Reads `.env`, runs a tiny Python one-liner that does:

```python
import asyncio, time
from shared.llm import build_llm
from langchain_core.messages import HumanMessage

async def main():
    llm = build_llm()
    t0 = time.time()
    r = await llm.ainvoke([HumanMessage("Reply with exactly one word: pong")])
    print(f"[{llm._llm_type}] {r.content.strip()!r} in {time.time()-t0:.2f}s")

asyncio.run(main())
```

Run: `./scripts/smoke-llm.sh`. Prints provider type, response, latency. Used after switching providers or changing env to verify connectivity.

### Manual validation after migration

1. `docker compose up`.
2. Open chat UI, log a skill: "slept 7h last night, score 82" → `agent-sleep`.
3. Verify row in `health_logs` (agent=sleep, type=sleep_session) — confirms sub-agent went through `build_llm()` and wrote through.
4. Repeat for workout and nutrition.
5. `/stats` endpoint shows the new entries.

## Error Handling

- `build_llm()` fails fast on unknown provider or missing required key. Raised at startup (module init or first call), not buried during a user request.
- `ChatClaudeCLI` errors surface as standard `RuntimeError` / `TimeoutError` — LangChain's normal error path.
- Provider-level errors (rate limits, auth failures) surface as the underlying library's exceptions (`anthropic.RateLimitError`, `openai.AuthenticationError`, etc.). Callers handle as today.

## Open Questions

None.

## Rollout

Single PR. The change is atomic (can't half-migrate — all call sites move together). No feature flag, no dual-write. `claude-cli` remains available as a provider so the previous flow is one env var away.

## Future Work (explicitly deferred)

- Per-agent provider override (`SLEEP_LLM_PROVIDER`).
- Streaming support for `ChatClaudeCLI` (would need `claude --print --output-format stream-json` parsing).
- Prompt caching configuration per provider (Anthropic supports it; OpenRouter/Gemini may need different flags).
- Cost tracking / usage metrics per call.
- Auto-fallback between providers.
