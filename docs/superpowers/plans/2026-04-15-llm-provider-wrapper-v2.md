# LLM Provider Wrapper v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bespoke Claude CLI subprocess in sub-agents with a shared `BaseChatModel`-based abstraction that supports five providers (anthropic, openrouter, gemini, ollama, claude-cli) via a single env switch.

**Architecture:** One shared module `shared/shared/llm.py` exposes `build_llm() -> BaseChatModel`. A custom `ChatClaudeCLI(BaseChatModel)` adapter wraps the Claude CLI subprocess so the subscription path stays selectable without being a special case. Sub-agents and orchestrator both import from `shared.llm`. No per-agent overrides, no registry — global env only. Third parties plug in new providers by writing their own `BaseChatModel` subclass (LangChain's documented extension point).

**Tech Stack:** Python 3.12, LangChain (`langchain-core`, `langchain-anthropic`, `langchain-openai`, `langchain-google-genai`, `langchain-ollama`), pytest (asyncio_mode=auto), Docker Compose.

**Spec:** [docs/superpowers/specs/2026-04-15-llm-provider-wrapper-v2-design.md](../specs/2026-04-15-llm-provider-wrapper-v2-design.md)

---

## File Structure

| File | Purpose |
|---|---|
| `shared/shared/llm.py` | **New.** `build_llm()` factory reading env, returning configured `BaseChatModel`. |
| `shared/shared/chat_claude_cli.py` | **New.** `ChatClaudeCLI(BaseChatModel)` adapter wrapping the Claude CLI subprocess. |
| `shared/shared/claude_runner.py` | **Deleted.** Logic absorbed into `ChatClaudeCLI`. |
| `shared/pyproject.toml` | **Modified.** Add LangChain deps so every service (agents + orchestrator) gets them via `pip install -e /shared`. |
| `orchestrator/app/llm.py` | **Deleted.** Replaced by `shared.llm`. |
| `orchestrator/app/health_agent.py` | **Modified.** Import path change. |
| `orchestrator/requirements.txt` | **Modified.** Remove duplicated LC deps (now in shared). |
| `agents/sleep/app/executor.py` | **Modified.** Replace `run_claude` calls with `build_llm().ainvoke(...)`. |
| `agents/workout/app/executor.py` | **Modified.** Same. |
| `agents/nutrition/app/executor.py` | **Modified.** Same. |
| `tests/test_llm.py` | **New.** Unit tests for every branch of `build_llm()`. |
| `tests/test_chat_claude_cli.py` | **New.** Unit tests for `ChatClaudeCLI` subprocess behavior (mocked). |
| `scripts/smoke-llm.sh` | **New.** Ping→pong round-trip against configured provider. |
| `.env.example` | **Modified.** Document all five providers + their keys; default = `openrouter`. |
| `docker-compose.yml` | **Modified (minimal).** Ensure provider env vars pass through. |
| `RUNNING.md` | **Modified.** `export-auth.sh` now optional; document provider switching. |

---

## Task 1: Add LangChain deps to shared package

**Files:**
- Modify: `shared/pyproject.toml`
- Modify: `orchestrator/requirements.txt`

- [ ] **Step 1: Add LangChain deps to shared/pyproject.toml**

Replace the `dependencies` block with:

```toml
dependencies = [
    "asyncpg>=0.29",
    "qdrant-client>=1.9",
    "httpx>=0.27",
    "langchain-core>=0.3",
    "langchain-anthropic>=0.3",
    "langchain-openai>=0.3",
    "langchain-google-genai>=2.0",
    "langchain-ollama>=0.2",
    "anthropic>=0.39",
]
```

`anthropic>=0.39` is required because the orchestrator's OAuth-injection path (preserved in the new wrapper) builds a manual `anthropic.AsyncAnthropic` client.

- [ ] **Step 2: Remove duplicated LC deps from orchestrator/requirements.txt**

Replace file contents with:

```
fastapi>=0.111
uvicorn[standard]>=0.29
httpx>=0.27
asyncpg>=0.29
ag-ui-langgraph==0.0.32
a2a-sdk>=0.2.5
copilotkit>=0.1.39,<0.2
```

(Deleted lines: `langchain-anthropic>=0.3`, `langchain-openai>=0.3`. Shared package pulls them in. No other lines change.)

- [ ] **Step 3: Rebuild images to pick up the new shared deps**

Run: `docker compose build --no-cache agent-sleep agent-workout agent-nutrition orchestrator`
Expected: All four images build without errors; `pip install` output shows the new LC packages being installed.

- [ ] **Step 4: Commit**

```bash
git add shared/pyproject.toml orchestrator/requirements.txt
git commit -m "deps: centralize LangChain packages in shared

All services now pull langchain-core, langchain-anthropic,
langchain-openai, langchain-google-genai, langchain-ollama
through the shared package."
```

---

## Task 2: ChatClaudeCLI adapter — tests first

**Files:**
- Test: `tests/test_chat_claude_cli.py`

- [ ] **Step 1: Create the test file with all failing tests**

Create `tests/test_chat_claude_cli.py`:

```python
"""Unit tests for ChatClaudeCLI — mocks the subprocess, no real CLI calls."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult

from shared.chat_claude_cli import ChatClaudeCLI


@pytest.fixture(autouse=True)
def _fake_claude_on_path(monkeypatch, tmp_path):
    # Simulate `claude` being on PATH by stubbing shutil.which used inside the adapter.
    monkeypatch.setattr("shared.chat_claude_cli.shutil.which", lambda name: "/usr/bin/claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-oat-test-token")


def _fake_process(stdout: bytes = b"pong", stderr: bytes = b"", returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    proc.kill = AsyncMock()
    return proc


@pytest.mark.asyncio
async def test_agenerate_spawns_expected_cmd():
    llm = ChatClaudeCLI(model="claude-sonnet-4-6")
    with patch("shared.chat_claude_cli.asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_process())) as spawn:
        await llm._agenerate([HumanMessage("hello")])
    args, kwargs = spawn.call_args
    assert args[0] == "/usr/bin/claude"
    assert "--print" in args
    assert "--bare" in args
    assert "--model" in args and args[args.index("--model") + 1] == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_system_message_is_prepended_to_prompt():
    llm = ChatClaudeCLI()
    with patch("shared.chat_claude_cli.asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_process())) as spawn:
        await llm._agenerate([SystemMessage("you are a bot"), HumanMessage("hi")])
    args, _ = spawn.call_args
    # The last positional arg is the full prompt; system content is prepended.
    prompt = args[-1]
    assert prompt.startswith("you are a bot")
    assert "hi" in prompt


@pytest.mark.asyncio
async def test_returns_chatresult_with_aimessage():
    llm = ChatClaudeCLI()
    with patch("shared.chat_claude_cli.asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_process(b"pong"))):
        result = await llm._agenerate([HumanMessage("ping")])
    assert isinstance(result, ChatResult)
    assert len(result.generations) == 1
    msg = result.generations[0].message
    assert isinstance(msg, AIMessage)
    assert msg.content == "pong"


@pytest.mark.asyncio
async def test_subprocess_error_propagates():
    llm = ChatClaudeCLI()
    with patch("shared.chat_claude_cli.asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=_fake_process(b"", b"boom", returncode=2))):
        with pytest.raises(RuntimeError, match="boom"):
            await llm._agenerate([HumanMessage("x")])


@pytest.mark.asyncio
async def test_subprocess_timeout():
    llm = ChatClaudeCLI(timeout_seconds=0)  # trip immediately
    proc = AsyncMock()

    async def _never(*_a, **_kw):
        import asyncio
        await asyncio.sleep(10)

    proc.communicate = _never
    proc.kill = AsyncMock()
    proc.returncode = None
    with patch("shared.chat_claude_cli.asyncio.create_subprocess_exec",
               new=AsyncMock(return_value=proc)):
        with pytest.raises(TimeoutError):
            await llm._agenerate([HumanMessage("x")])


@pytest.mark.asyncio
async def test_missing_token_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    llm = ChatClaudeCLI()
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        await llm._agenerate([HumanMessage("x")])


def test_llm_type():
    assert ChatClaudeCLI()._llm_type == "claude-cli"
```

- [ ] **Step 2: Run tests and verify they fail with ImportError**

Run: `pytest tests/test_chat_claude_cli.py -v`
Expected: ImportError on `from shared.chat_claude_cli import ChatClaudeCLI` (module doesn't exist yet).

---

## Task 3: Implement ChatClaudeCLI

**Files:**
- Create: `shared/shared/chat_claude_cli.py`

- [ ] **Step 1: Write the adapter**

Create `shared/shared/chat_claude_cli.py`:

```python
"""ChatClaudeCLI — a BaseChatModel adapter around the `claude` CLI subprocess.

Known limitations (documented here, not bugs):
- No streaming (the CLI's --print mode emits the full reply at once).
- No tool calling.
- No structured output.
- Requires ANTHROPIC_API_KEY in env (OAuth token from macOS Keychain via
  scripts/export-auth.sh). Token expires ~every 8h.
"""
from __future__ import annotations

import asyncio
import os
import shutil
from typing import Any, List, Optional

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ChatClaudeCLI(BaseChatModel):
    """LangChain chat model that shells out to the `claude` CLI.

    Uses `claude --print --bare --model {model}` with ANTHROPIC_API_KEY
    (OAuth token) in the child process env. Messages become a single
    concatenated prompt; any SystemMessage content is passed via
    `--system-prompt` instead of stdin.
    """

    model: str = "claude-sonnet-4-6"
    timeout_seconds: int = 120

    @property
    def _llm_type(self) -> str:
        return "claude-cli"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.model}

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        return asyncio.run(self._agenerate(messages, stop, None, **kwargs))

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        token = os.environ.get("ANTHROPIC_API_KEY", "")
        if not token:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Run scripts/export-auth.sh to export "
                "the OAuth token from Keychain before starting containers."
            )
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError("claude CLI not found in PATH")

        prompt = self._flatten_messages(messages)

        cmd: list[str] = [claude_bin, "--print", "--bare", "--model", self.model, prompt]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "ANTHROPIC_API_KEY": token},
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout_seconds
            )
        except asyncio.TimeoutError as e:
            await proc.kill()
            raise TimeoutError(
                f"claude CLI timed out after {self.timeout_seconds}s"
            ) from e

        if proc.returncode != 0:
            err = (stderr or b"").decode(errors="replace")[:500]
            raise RuntimeError(f"claude exited {proc.returncode}: {err}")

        text = (stdout or b"").decode(errors="replace").strip()
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))]
        )

    @staticmethod
    def _flatten_messages(messages: List[BaseMessage]) -> str:
        """Join all messages (system first, then the rest in order) into a single
        prompt string. The CLI's --print mode takes one positional prompt arg and
        has no native role separation, so we flatten."""
        system_parts: list[str] = []
        other_parts: list[str] = []
        for m in messages:
            if isinstance(m, SystemMessage):
                system_parts.append(str(m.content))
            else:
                other_parts.append(str(m.content))
        return "\n\n".join(system_parts + other_parts).strip()
```

- [ ] **Step 2: Run tests and verify they pass**

Run: `pytest tests/test_chat_claude_cli.py -v`
Expected: all 7 tests pass.

- [ ] **Step 3: Commit**

```bash
git add shared/shared/chat_claude_cli.py tests/test_chat_claude_cli.py
git commit -m "feat(shared): ChatClaudeCLI BaseChatModel adapter

Wraps the claude --print --bare subprocess as a standard LangChain
BaseChatModel so the subscription path is selectable via build_llm()
like any other provider."
```

---

## Task 4: build_llm() factory — tests first

**Files:**
- Test: `tests/test_llm.py`

- [ ] **Step 1: Create the test file**

Create `tests/test_llm.py`:

```python
"""Unit tests for shared.llm.build_llm — pure env-driven, no network."""
from __future__ import annotations

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from shared.chat_claude_cli import ChatClaudeCLI
from shared.llm import build_llm


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY",
              "OPENROUTER_API_KEY", "GEMINI_API_KEY", "OLLAMA_HOST"):
        monkeypatch.delenv(k, raising=False)


def test_default_provider_is_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    llm = build_llm()
    assert isinstance(llm, ChatOpenAI)
    assert str(llm.openai_api_base).rstrip("/") == "https://openrouter.ai/api/v1"
    assert llm.model_name == "meta-llama/llama-3.3-70b-instruct:free"


def test_anthropic_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-k")
    llm = build_llm()
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-sonnet-4-6"


def test_anthropic_oauth_token_injects_manual_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-oat-xyz")
    llm = build_llm()
    # OAuth path replaces the SDK client slots so the Bearer header is used.
    assert "_async_client" in llm.__dict__
    assert "_client" in llm.__dict__


def test_openrouter_explicit_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    llm = build_llm()
    assert isinstance(llm, ChatOpenAI)
    assert str(llm.openai_api_base).rstrip("/") == "https://openrouter.ai/api/v1"


def test_gemini_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    llm = build_llm()
    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert llm.model.endswith("gemini-2.0-flash-exp")


def test_ollama_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    llm = build_llm()
    assert isinstance(llm, ChatOllama)
    assert llm.model == "llama3.1:8b"


def test_claude_cli_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude-cli")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-oat-xyz")
    llm = build_llm()
    assert isinstance(llm, ChatClaudeCLI)
    assert llm.model == "claude-sonnet-4-6"


def test_llm_model_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "custom/model-x")
    llm = build_llm()
    assert llm.model == "custom/model-x"


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    with pytest.raises(ValueError, match="unknown provider"):
        build_llm()


@pytest.mark.parametrize(
    "provider,key",
    [
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"),
        ("gemini", "GEMINI_API_KEY"),
        ("claude-cli", "ANTHROPIC_API_KEY"),
    ],
)
def test_missing_api_key_raises(monkeypatch, provider, key):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match=key):
        build_llm()
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `pytest tests/test_llm.py -v`
Expected: ImportError on `from shared.llm import build_llm` (module doesn't exist yet).

---

## Task 5: Implement build_llm()

**Files:**
- Create: `shared/shared/llm.py`

- [ ] **Step 1: Write the factory**

Create `shared/shared/llm.py`:

```python
"""LLM provider factory shared by orchestrator and all sub-agents.

Public surface: a single function `build_llm() -> BaseChatModel`.

Env vars:
    LLM_PROVIDER — one of: anthropic | openrouter | gemini | ollama | claude-cli
                   (default: openrouter).
    LLM_MODEL    — optional override. Each provider has a default (see below).

Required key per provider:
    anthropic   — ANTHROPIC_API_KEY
    openrouter  — OPENROUTER_API_KEY
    gemini      — GEMINI_API_KEY
    ollama      — (none; OLLAMA_HOST optional, defaults to http://localhost:11434)
    claude-cli  — ANTHROPIC_API_KEY  (OAuth token from scripts/export-auth.sh)

Unknown provider → ValueError. Missing required key → ValueError.

Third-party extension: write your own BaseChatModel subclass per the LangChain
docs and instantiate it directly in application code — this factory covers
the shipped providers only.
"""
from __future__ import annotations

import os

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from .chat_claude_cli import ChatClaudeCLI


_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "gemini": "gemini-2.0-flash-exp",
    "ollama": "llama3.1:8b",
    "claude-cli": "claude-sonnet-4-6",
}


def build_llm() -> BaseChatModel:
    provider = os.environ.get("LLM_PROVIDER", "openrouter").lower()
    if provider not in _DEFAULT_MODELS:
        raise ValueError(
            f"unknown provider: {provider!r}. Supported: {sorted(_DEFAULT_MODELS)}"
        )
    model = os.environ.get("LLM_MODEL") or _DEFAULT_MODELS[provider]

    if provider == "anthropic":
        return _build_anthropic(model)
    if provider == "openrouter":
        return _build_openrouter(model)
    if provider == "gemini":
        return _build_gemini(model)
    if provider == "ollama":
        return _build_ollama(model)
    if provider == "claude-cli":
        return _build_claude_cli(model)
    # Unreachable — the membership check above guards this.
    raise ValueError(f"unknown provider: {provider!r}")


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise ValueError(f"{key} not set")
    return val


def _build_anthropic(model: str) -> BaseChatModel:
    token = _require("ANTHROPIC_API_KEY")
    llm = ChatAnthropic(model=model, temperature=0)
    # OAuth tokens (sk-ant-oat*) must be sent as Authorization: Bearer with
    # anthropic-beta: oauth-2025-04-20. Inject a manual SDK client into
    # ChatAnthropic's cached slots so LangChain uses it.
    if token.startswith("sk-ant-oat"):
        headers = {"anthropic-beta": "oauth-2025-04-20"}
        llm.__dict__["_async_client"] = anthropic.AsyncAnthropic(
            api_key="", auth_token=token, default_headers=headers,
        )
        llm.__dict__["_client"] = anthropic.Anthropic(
            api_key="", auth_token=token, default_headers=headers,
        )
    return llm


def _build_openrouter(model: str) -> BaseChatModel:
    return ChatOpenAI(
        model=model,
        temperature=0,
        api_key=_require("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
    )


def _build_gemini(model: str) -> BaseChatModel:
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=0,
        google_api_key=_require("GEMINI_API_KEY"),
    )


def _build_ollama(model: str) -> BaseChatModel:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    return ChatOllama(model=model, temperature=0, base_url=host)


def _build_claude_cli(model: str) -> BaseChatModel:
    _require("ANTHROPIC_API_KEY")
    return ChatClaudeCLI(model=model)
```

- [ ] **Step 2: Run tests and verify they pass**

Run: `pytest tests/test_llm.py tests/test_chat_claude_cli.py -v`
Expected: all tests pass (7 from ChatClaudeCLI + 11 from build_llm).

- [ ] **Step 3: Commit**

```bash
git add shared/shared/llm.py tests/test_llm.py
git commit -m "feat(shared): build_llm() factory across five providers

One env switch (LLM_PROVIDER) picks anthropic, openrouter, gemini,
ollama, or claude-cli. Default is openrouter with a free model."
```

---

## Task 6: Migrate orchestrator

**Files:**
- Modify: `orchestrator/app/health_agent.py`
- Delete: `orchestrator/app/llm.py`

- [ ] **Step 1: Update orchestrator import**

In `orchestrator/app/health_agent.py`, find:

```python
from .llm import build_llm
```

Replace with:

```python
from shared.llm import build_llm
```

- [ ] **Step 2: Delete the old module**

Run: `rm orchestrator/app/llm.py`

- [ ] **Step 3: Bring the container up and smoke-test the chat**

Run: `scripts/export-auth.sh && docker compose up -d orchestrator`
Then open the chat UI (nginx/frontend) and send "how did I sleep yesterday?".
Expected: response streams back normally; orchestrator logs show `LLM_PROVIDER` resolved to whatever `.env` specifies, no import errors.

- [ ] **Step 4: Commit**

```bash
git add orchestrator/app/health_agent.py
git rm orchestrator/app/llm.py
git commit -m "refactor(orchestrator): use shared.llm.build_llm

Delete orchestrator/app/llm.py — its logic now lives in
shared/shared/llm.py and is reused across all services."
```

---

## Task 7: Migrate sleep agent

**Files:**
- Modify: `agents/sleep/app/executor.py`

- [ ] **Step 1: Replace run_claude import + call sites**

In `agents/sleep/app/executor.py`:

Remove line:
```python
from shared.claude_runner import run_claude
```

Add after the other `shared.*` imports:
```python
from langchain_core.messages import HumanMessage
from shared.llm import build_llm

_LLM = build_llm()
```

Find `_infer_skill_via_llm` and replace the `run_claude` call block:

```python
try:
    raw = await asyncio.to_thread(run_claude, prompt, 30)
except Exception as e:
    logger.warning("LLM skill inference failed: %s", e)
    return None
```

With:

```python
try:
    result = await _LLM.ainvoke([HumanMessage(prompt)])
    raw = result.content if isinstance(result.content, str) else str(result.content)
except Exception as e:
    logger.warning("LLM skill inference failed: %s", e)
    return None
```

Find the main-path call:
```python
output = await asyncio.to_thread(run_claude, prompt)
```

Replace with:
```python
result = await _LLM.ainvoke([HumanMessage(prompt)])
output = result.content if isinstance(result.content, str) else str(result.content)
```

Also update the `cancel` method's stale TODO comment:

```python
async def cancel(self, ctx: RequestContext, event_queue: EventQueue) -> None:
    # cancel() enqueues a canceled status; it does NOT abort an in-flight
    # LLM request. Proper cancellation would require threading a cancel
    # token through shared.llm.
    await _emit_status(event_queue, ctx.task_id, ctx.context_id, TaskState.canceled, final=True)
```

- [ ] **Step 2: Rebuild and restart the sleep agent**

Run: `docker compose build agent-sleep && docker compose up -d agent-sleep`
Expected: builds and starts without errors.

- [ ] **Step 3: Exercise the agent end-to-end**

Run:
```bash
curl -s http://localhost:8001/.well-known/agent.json | head
```
Expected: agent card JSON prints (confirms the service is up).

Then send a log message through the chat UI: "slept 7h last night, score 82".
Expected: response appears in the UI; a new `sleep_session` row in Postgres:
```bash
docker compose exec postgres psql -U postgres -d life_agents -c \
  "SELECT agent, type, recorded_at FROM health_logs ORDER BY recorded_at DESC LIMIT 3;"
```

- [ ] **Step 4: Commit**

```bash
git add agents/sleep/app/executor.py
git commit -m "refactor(sleep): migrate from run_claude to shared.llm

The agent now goes through build_llm() like the orchestrator. No
behavior change with LLM_PROVIDER=claude-cli; other providers
become selectable without code edits."
```

---

## Task 8: Migrate workout agent

**Files:**
- Modify: `agents/workout/app/executor.py`

- [ ] **Step 1: Apply the same three edits as Task 7**

Same pattern: delete the `from shared.claude_runner import run_claude` line, add the two new imports and `_LLM = build_llm()` at module scope, replace both `run_claude` call sites with `await _LLM.ainvoke([HumanMessage(prompt)])` and `.content` extraction, update the stale cancel TODO comment.

Concretely, in `agents/workout/app/executor.py`:

1. Remove: `from shared.claude_runner import run_claude`
2. Add after other `shared.*` imports:
   ```python
   from langchain_core.messages import HumanMessage
   from shared.llm import build_llm

   _LLM = build_llm()
   ```
3. Replace every `await asyncio.to_thread(run_claude, prompt)` call with:
   ```python
   result = await _LLM.ainvoke([HumanMessage(prompt)])
   output = result.content if isinstance(result.content, str) else str(result.content)
   ```
   (If the call is inside `_infer_skill_via_llm`, name the variable `raw` instead of `output` to match existing downstream code.)
4. In `cancel`, replace any TODO comment referencing `claude-runner.py` / Popen with the new comment from Task 7 Step 1.

- [ ] **Step 2: Rebuild and restart**

Run: `docker compose build agent-workout && docker compose up -d agent-workout`

- [ ] **Step 3: End-to-end check**

Send through chat UI: "runned 5km this morning".
Expected: response appears; activity row in Postgres.

- [ ] **Step 4: Commit**

```bash
git add agents/workout/app/executor.py
git commit -m "refactor(workout): migrate from run_claude to shared.llm"
```

---

## Task 9: Migrate nutrition agent

**Files:**
- Modify: `agents/nutrition/app/executor.py`

- [ ] **Step 1: Apply the same three edits as Task 7**

Identical pattern to Tasks 7 and 8. In `agents/nutrition/app/executor.py`:

1. Remove: `from shared.claude_runner import run_claude`
2. Add after other `shared.*` imports:
   ```python
   from langchain_core.messages import HumanMessage
   from shared.llm import build_llm

   _LLM = build_llm()
   ```
3. Replace every `await asyncio.to_thread(run_claude, prompt)` call with:
   ```python
   result = await _LLM.ainvoke([HumanMessage(prompt)])
   output = result.content if isinstance(result.content, str) else str(result.content)
   ```
   Rename to `raw` inside `_infer_skill_via_llm`.
4. Update the cancel-method TODO comment as in Task 7.

- [ ] **Step 2: Rebuild and restart**

Run: `docker compose build agent-nutrition && docker compose up -d agent-nutrition`

- [ ] **Step 3: End-to-end check**

Send through chat UI: "had oatmeal for breakfast, about 400 kcal".
Expected: response appears; meal row in Postgres.

- [ ] **Step 4: Commit**

```bash
git add agents/nutrition/app/executor.py
git commit -m "refactor(nutrition): migrate from run_claude to shared.llm"
```

---

## Task 10: Remove shared/claude_runner.py

**Files:**
- Delete: `shared/shared/claude_runner.py`

- [ ] **Step 1: Verify there are no more references**

Run: `rg -n "claude_runner|run_claude" --glob '!docs/**' --glob '!logs/**'`
Expected: no matches (or only matches inside `shared/claude_runner.py` itself).

If any non-doc matches appear, they were missed in Tasks 6–9. Go back and fix before deleting.

- [ ] **Step 2: Delete the module**

Run: `rm shared/shared/claude_runner.py`

- [ ] **Step 3: Commit**

```bash
git rm shared/shared/claude_runner.py
git commit -m "chore(shared): drop claude_runner.py

All call sites migrated to shared.llm.build_llm + BaseChatModel in
Tasks 6–9; the bespoke subprocess wrapper is no longer used.
ChatClaudeCLI (Task 2/3) preserves the subscription path as one
of the build_llm() providers."
```

---

## Task 11: Smoke script

**Files:**
- Create: `scripts/smoke-llm.sh`

- [ ] **Step 1: Write the script**

Create `scripts/smoke-llm.sh`:

```bash
#!/usr/bin/env bash
# Minimal LLM provider smoke test.
# Reads .env from repo root, builds the configured LLM via shared.llm.build_llm,
# sends a one-word ping, prints the reply and latency.
set -euo pipefail

cd "$(dirname "$0")/.."

# Load .env if present (export every VAR=VAL line)
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi
if [ -f .env.auth ]; then
  set -a; . ./.env.auth; set +a
fi

python -c '
import asyncio, time, os
from shared.llm import build_llm
from langchain_core.messages import HumanMessage

async def main():
    llm = build_llm()
    t0 = time.time()
    r = await llm.ainvoke([HumanMessage("Reply with exactly one word: pong")])
    content = r.content if isinstance(r.content, str) else str(r.content)
    provider = os.environ.get("LLM_PROVIDER", "openrouter")
    print(f"[{llm._llm_type} via {provider}] {content.strip()!r} in {time.time()-t0:.2f}s")

asyncio.run(main())
'
```

- [ ] **Step 2: Make it executable and run it**

Run:
```bash
chmod +x scripts/smoke-llm.sh
./scripts/smoke-llm.sh
```

Expected: prints a line like `[openai-chat via openrouter] 'pong' in 1.43s` (exact `_llm_type` depends on provider). Non-zero exit on any error. If the current `.env` lacks the provider's API key, it errors with `ValueError: {KEY} not set` — that's correct behavior.

- [ ] **Step 3: Commit**

```bash
git add scripts/smoke-llm.sh
git commit -m "chore(scripts): add smoke-llm.sh for provider round-trip"
```

---

## Task 12: Docs + env

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `RUNNING.md`

- [ ] **Step 1: Update .env.example**

Replace (or add if missing) the LLM section:

```bash
# -------- LLM provider --------
# One of: anthropic | openrouter | gemini | ollama | claude-cli
LLM_PROVIDER=openrouter
# Optional override. Each provider has a sensible default.
# LLM_MODEL=

# Set the key that matches LLM_PROVIDER:
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=
GEMINI_API_KEY=
# OLLAMA_HOST=http://host.docker.internal:11434  # only for ollama from Docker

# claude-cli: ANTHROPIC_API_KEY is populated by scripts/export-auth.sh
# (OAuth token from macOS Keychain). Token expires ~8h.
```

- [ ] **Step 2: Confirm docker-compose passes vars through**

Check that each of `agent-sleep`, `agent-workout`, `agent-nutrition`, `orchestrator` uses `env_file: .env` (they already do). No changes needed unless the file is missing `env_file:` for any of those services.

If `env_file: .env` is already present on all four services, skip edits here. Otherwise add `env_file: .env` under each service definition.

- [ ] **Step 3: Update RUNNING.md**

Find the startup section that references `scripts/export-auth.sh` and replace the paragraph explaining it with:

```markdown
## LLM provider

Set `LLM_PROVIDER` in `.env` to one of: `anthropic`, `openrouter`, `gemini`,
`ollama`, `claude-cli`. Default is `openrouter` with a free model. Set the
matching API key.

- **OpenRouter / Anthropic / Gemini:** just set the API key. Plain HTTP.
- **Ollama:** run Ollama on the host; set `OLLAMA_HOST=http://host.docker.internal:11434`.
- **Claude CLI (subscription):** run `scripts/export-auth.sh` before `docker compose up`
  to export your OAuth token from macOS Keychain. Token expires every ~8h —
  re-run the script when you see 401 errors.

Switch providers with a single env change + `docker compose restart`.
```

- [ ] **Step 4: Commit**

```bash
git add .env.example RUNNING.md docker-compose.yml
git commit -m "docs: document LLM_PROVIDER and provider-specific setup

Default provider is openrouter (free model); claude-cli + export-auth.sh
is now one option of five rather than a required step."
```

---

## Task 13: Final end-to-end validation

No code changes — this task verifies the whole stack works under two different providers.

- [ ] **Step 1: Run unit tests**

Run: `pytest tests/test_llm.py tests/test_chat_claude_cli.py -v`
Expected: all tests pass.

- [ ] **Step 2: Run the smoke with the default provider (OpenRouter)**

Set in `.env`: `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY=...`.
Run: `./scripts/smoke-llm.sh`
Expected: one-word reply within a few seconds.

- [ ] **Step 3: Run the full stack on OpenRouter**

Run: `docker compose up -d`
In the chat UI, send three messages and confirm each hits the right agent:
- "slept 7h last night, score 82" → sleep log row in Postgres
- "ran 5km this morning" → workout activity row
- "had eggs and toast, ~350 kcal" → nutrition meal row

Run:
```bash
docker compose exec postgres psql -U postgres -d life_agents -c \
  "SELECT agent, type, source, recorded_at FROM health_logs ORDER BY recorded_at DESC LIMIT 5;"
```
Expected: three new rows (one per agent).

- [ ] **Step 4: Repeat with LLM_PROVIDER=claude-cli**

Change `.env`: `LLM_PROVIDER=claude-cli`. Run `scripts/export-auth.sh` then `docker compose restart`.
Repeat Step 3's three messages.
Expected: same behavior — three new rows. Confirms the CLI path still works via `ChatClaudeCLI`.

- [ ] **Step 5: Commit nothing; close the loop**

If everything passes, the plan is done. If a step fails, fix forward with a targeted commit; do not roll back the migration.
