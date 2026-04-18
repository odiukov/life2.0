"""Hermetic unit tests for the create_health_agent checkpointer seam.

These run without a live Postgres — they only verify the wiring that
main.lifespan depends on. End-to-end durability is covered by
scripts/smoke-checkpointer.sh.
"""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.app.health_agent import create_health_agent


@pytest.mark.asyncio
async def test_create_health_agent_uses_provided_checkpointer():
    saver = MemorySaver()
    graph = await create_health_agent(checkpointer=saver)
    assert graph.checkpointer is saver


@pytest.mark.asyncio
async def test_create_health_agent_defaults_to_memory_saver():
    graph = await create_health_agent()
    assert isinstance(graph.checkpointer, MemorySaver)
