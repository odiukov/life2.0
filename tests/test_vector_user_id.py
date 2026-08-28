"""Contract test: vector.search_memories always applies a user_id filter."""
from __future__ import annotations

import inspect
from uuid import UUID

from shared import vector

USER_A = UUID("11111111-1111-1111-1111-111111111111")


def test_upsert_memory_signature_has_user_id_first():
    sig = inspect.signature(vector.upsert_memory)
    params = list(sig.parameters)
    assert params[0] == "user_id", f"expected user_id first, got {params}"


def test_search_memories_signature_has_user_id_first():
    sig = inspect.signature(vector.search_memories)
    params = list(sig.parameters)
    assert params[0] == "user_id", f"expected user_id first, got {params}"
