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
os.environ.setdefault("POSTGRES_DSN", "postgresql://lifeagents:lifeagents@localhost:5432/lifeagents")


# Fixed UUID for integration tests. Seeded into public.users by ensure_test_user.
import uuid as _uuid
TEST_USER_ID = _uuid.UUID("11111111-1111-1111-1111-111111111111")


async def ensure_test_user() -> _uuid.UUID:
    """Idempotently insert TEST_USER_ID into public.users so FKs satisfy.

    Integration tests on per-user tables call this before exercising the
    code under test. Safe to call repeatedly; uses ON CONFLICT DO NOTHING.
    """
    import asyncpg
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute(
            "INSERT INTO public.users (id, name) VALUES ($1, 'pytest-fixture-user') "
            "ON CONFLICT (id) DO NOTHING",
            TEST_USER_ID,
        )
    finally:
        await conn.close()
    return TEST_USER_ID
