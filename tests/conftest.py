"""Test environment defaults.

Pytest collects some test modules that import the orchestrator app, which
constructs its LangGraph at import time and therefore needs a valid LLM
provider env. Real keys aren't needed for unit tests (the LLM clients are
mocked or never invoked), so we set placeholder values early — before any
test module is imported.
"""
from __future__ import annotations

import os

# Order matters: these run before pytest imports any test module.
os.environ.setdefault("LLM_PROVIDER", "openrouter")
os.environ.setdefault("OPENROUTER_API_KEY", "test-placeholder")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-placeholder")
os.environ.setdefault("GEMINI_API_KEY", "test-placeholder")
os.environ.setdefault("GROQ_API_KEY", "test-placeholder")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-placeholder")
