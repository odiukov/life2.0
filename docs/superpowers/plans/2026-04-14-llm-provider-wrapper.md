# LLM Provider Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provider-switching factory so `health_agent` can use either Anthropic (default, OAuth-token) or OpenRouter (OpenAI-compatible) via an env var, without changing behavior for existing users.

**Architecture:** New module `orchestrator/app/llm.py` exposes `build_llm() -> BaseChatModel`. Reads `LLM_PROVIDER` (`anthropic` | `openrouter`), `LLM_MODEL` (optional override), and the provider's API key. The Anthropic branch preserves the current OAuth client injection; the OpenRouter branch returns `ChatOpenAI` pointed at `https://openrouter.ai/api/v1`. `health_agent.py` drops its local `_build_llm()` and imports from `llm.py`.

**Tech Stack:** Python 3.12, LangChain (`langchain-anthropic`, `langchain-openai`), pytest (asyncio_mode=auto), Docker Compose.

**Spec:** [docs/superpowers/specs/2026-04-14-llm-provider-wrapper-design.md](../specs/2026-04-14-llm-provider-wrapper-design.md)

---

## File Structure

| File | Purpose |
|---|---|
| `orchestrator/app/llm.py` | **New.** `build_llm()` factory, reads env, returns configured `BaseChatModel`. |
| `orchestrator/app/health_agent.py` | **Modified.** Remove local `_build_llm()` + `anthropic`/`ChatAnthropic` imports; import `build_llm` from `.llm`. |
| `orchestrator/requirements.txt` | **Modified.** Add `langchain-openai>=0.3`. |
| `.env.example` | **Modified.** Add `LLM_PROVIDER`, `LLM_MODEL`, `OPENROUTER_API_KEY`. |
| `tests/test_llm_provider.py` | **New.** Unit tests for `build_llm()`. |

---

## Task 1: Add dependency and failing tests for the factory

**Files:**
- Modify: `orchestrator/requirements.txt`
- Create: `tests/test_llm_provider.py`

- [ ] **Step 1: Add `langchain-openai` to requirements**

Append to `orchestrator/requirements.txt`:

```
langchain-openai>=0.3
```

- [ ] **Step 2: Install locally so tests can run**

Run: `pip install 'langchain-openai>=0.3'`
Expected: installs without conflicts.

- [ ] **Step 3: Write failing tests for `build_llm()`**

Create `tests/test_llm_provider.py`:

```python
import os

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from orchestrator.app.llm import build_llm


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for key in ("LLM_PROVIDER", "LLM_MODEL", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def test_default_provider_is_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-plainkey")
    llm = build_llm()
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-sonnet-4-6"


def test_anthropic_oauth_token_injects_client(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-oat01-testtoken")
    llm = build_llm()
    assert isinstance(llm, ChatAnthropic)
    async_client = llm.__dict__["_async_client"]
    assert async_client.auth_token == "sk-ant-oat01-testtoken"
    assert async_client.default_headers.get("anthropic-beta") == "oauth-2025-04-20"


def test_anthropic_respects_llm_model_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-x")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5-20251001")
    llm = build_llm()
    assert isinstance(llm, ChatAnthropic)
    assert llm.model == "claude-haiku-4-5-20251001"


def test_openrouter_returns_chatopenai_with_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    llm = build_llm()
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "openrouter/elephant-alpha"
    assert str(llm.openai_api_base) == "https://openrouter.ai/api/v1"


def test_openrouter_respects_llm_model_override(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("LLM_MODEL", "deepseek/deepseek-chat-v3.1:free")
    llm = build_llm()
    assert llm.model_name == "deepseek/deepseek-chat-v3.1:free"


def test_openrouter_missing_key_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    with pytest.raises(KeyError):
        build_llm()


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        build_llm()
```

- [ ] **Step 4: Run tests, confirm they fail with ImportError**

Run: `pytest tests/test_llm_provider.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'orchestrator.app.llm').

- [ ] **Step 5: Commit**

```bash
git add orchestrator/requirements.txt tests/test_llm_provider.py
git commit -m "test: failing tests for LLM provider factory"
```

---

## Task 2: Implement `build_llm()` factory

**Files:**
- Create: `orchestrator/app/llm.py`

- [ ] **Step 1: Write `orchestrator/app/llm.py`**

```python
# orchestrator/app/llm.py
"""LLM provider factory for the health agent.

Reads env vars at call time and returns a configured chat model:

- LLM_PROVIDER: "anthropic" (default) or "openrouter".
- LLM_MODEL: optional override. Defaults per provider below.
- ANTHROPIC_API_KEY / OPENROUTER_API_KEY: required for the selected provider.
"""
import os

import anthropic
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openrouter": "openrouter/elephant-alpha",
}


def build_llm() -> BaseChatModel:
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider not in _DEFAULT_MODELS:
        raise ValueError(
            f"Unknown LLM_PROVIDER={provider!r}. "
            f"Supported: {sorted(_DEFAULT_MODELS)}"
        )

    model = os.environ.get("LLM_MODEL") or _DEFAULT_MODELS[provider]

    if provider == "openrouter":
        return ChatOpenAI(
            model=model,
            temperature=0,
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        )

    # provider == "anthropic"
    # OAuth tokens (sk-ant-oat*) must be sent as Authorization: Bearer with
    # the anthropic-beta: oauth-2025-04-20 header. Inject a manually-built
    # SDK client into ChatAnthropic's cached client slots so LangChain uses it.
    token = os.environ.get("ANTHROPIC_API_KEY", "")
    is_oauth = token.startswith("sk-ant-oat")
    llm = ChatAnthropic(model=model, temperature=0)
    if is_oauth:
        headers = {"anthropic-beta": "oauth-2025-04-20"}
        llm.__dict__["_async_client"] = anthropic.AsyncAnthropic(
            api_key="", auth_token=token, default_headers=headers,
        )
        llm.__dict__["_client"] = anthropic.Anthropic(
            api_key="", auth_token=token, default_headers=headers,
        )
    return llm
```

- [ ] **Step 2: Run tests, verify all pass**

Run: `pytest tests/test_llm_provider.py -v`
Expected: 7 PASSED.

- [ ] **Step 3: Commit**

```bash
git add orchestrator/app/llm.py
git commit -m "feat: add LLM provider factory (Anthropic/OpenRouter)"
```

---

## Task 3: Wire `health_agent.py` to use the factory

**Files:**
- Modify: `orchestrator/app/health_agent.py`

- [ ] **Step 1: Replace the import block and remove `_build_llm()`**

At the top of `orchestrator/app/health_agent.py`, change:

```python
import os
import uuid
import warnings

import anthropic
import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool


def _build_llm() -> ChatAnthropic:
    """Build ChatAnthropic configured for Claude Code OAuth tokens.
    ...
    """
    token = os.environ.get("ANTHROPIC_API_KEY", "")
    is_oauth = token.startswith("sk-ant-oat")

    llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)

    if is_oauth:
        headers = {"anthropic-beta": "oauth-2025-04-20"}
        llm.__dict__["_async_client"] = anthropic.AsyncAnthropic(
            api_key="", auth_token=token, default_headers=headers,
        )
        llm.__dict__["_client"] = anthropic.Anthropic(
            api_key="", auth_token=token, default_headers=headers,
        )
    return llm
```

...to:

```python
import uuid
import warnings

import httpx
from langchain_core.tools import tool

from .llm import build_llm
```

Note: `os` is still used later in the file (grep before removing). If `os` is no longer referenced anywhere else in the file, remove it too; otherwise keep it.

- [ ] **Step 2: Replace the call site in `create_health_agent()`**

Inside `create_health_agent()`, change:

```python
    llm = _build_llm()
```

...to:

```python
    llm = build_llm()
```

- [ ] **Step 3: Verify `os` usage — remove import if unused**

Run: `grep -n "\bos\." orchestrator/app/health_agent.py`
If no matches remain, remove `import os` from the file. If matches remain, keep it.

- [ ] **Step 4: Run existing orchestrator tests**

Run: `pytest tests/test_orchestrator_routing.py tests/test_orchestrator_stats.py tests/test_orchestrator_stream.py -v`
Expected: all PASS (no regression; `health_agent` import should not raise).

- [ ] **Step 5: Import-smoke-test `health_agent` directly**

Run: `ANTHROPIC_API_KEY=sk-ant-oat01-smoke python -c "from orchestrator.app.health_agent import create_health_agent; create_health_agent()"`
Expected: exits 0 with no traceback.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/app/health_agent.py
git commit -m "refactor: use llm.build_llm() in health_agent"
```

---

## Task 4: Document env vars in `.env.example`

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Append to `.env.example`**

Append these lines (preserve existing content):

```
# LLM provider for the health agent: anthropic (default) | openrouter
LLM_PROVIDER=anthropic
# Optional model override. Defaults: claude-sonnet-4-6 (anthropic) /
# openrouter/elephant-alpha (openrouter).
# LLM_MODEL=
# Required when LLM_PROVIDER=openrouter. Get a key at https://openrouter.ai/keys
OPENROUTER_API_KEY=
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: document LLM_PROVIDER / OPENROUTER_API_KEY in .env.example"
```

---

## Task 5: Manual end-to-end verification with OpenRouter

**Files:** none (runtime verification)

- [ ] **Step 1: Add `OPENROUTER_API_KEY` to `.env`**

Edit `.env` (not committed) and set your real key:

```
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-...
```

- [ ] **Step 2: Rebuild and restart orchestrator**

Run: `docker compose build orchestrator && docker compose up -d orchestrator copilotkit-runtime`
Expected: both containers healthy.

- [ ] **Step 3: Check logs for successful startup**

Run: `docker compose logs --tail=30 orchestrator`
Expected: `Uvicorn running on http://0.0.0.0:8000`, no tracebacks.

- [ ] **Step 4: Send a health question via frontend**

Open http://localhost:3000, ask: "Как я спал вчера?"
Expected:
- Chat stream completes (no `INCOMPLETE_STREAM` error in browser console).
- The response includes sleep data (confirms the tool call to `analyze_sleep` reached the sub-agent).
- `docker compose logs copilotkit-runtime` shows no errors.

- [ ] **Step 5: Flip back to Anthropic and confirm legacy path still works**

Set `LLM_PROVIDER=anthropic` in `.env`, run `./scripts/refresh-auth.sh`, then ask the same question via the frontend.
Expected: works exactly as before (subject to upstream rate limits).

- [ ] **Step 6: Commit the .env.example changes only if any additional tweaks needed**

(No code commit for this verification task unless issues were found. If the chosen OpenRouter model doesn't support tool calls, set `LLM_MODEL=deepseek/deepseek-chat-v3.1:free` in `.env` as a fallback and rerun from Step 2.)

---

## Out of Scope

- Auto-fallback between providers (explicit decision in the spec).
- Changing sub-agents (sleep/workout/nutrition) — they use the Claude CLI.
- Adding retry/backoff logic on 429.
