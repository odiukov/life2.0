"""LangGraph AsyncPostgresSaver lifecycle for the orchestrator.

Owns a psycopg3 AsyncConnectionPool separate from the asyncpg pool in
shared/shared/db.py. The two pools never share a connection:
    - asyncpg  owns health_logs / tasks / habits (domain tables).
    - psycopg3 owns LangGraph's checkpoint tables (LangGraph manages the
      schema itself via `await saver.setup()`).

Production pattern: externally-managed pool with autocommit=True and
prepare_threshold=0, per LangChain's production guidance. `from_conn_string`
is avoided because it hides the pool and can leak connections.
"""
from __future__ import annotations

import logging
import os

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

_POOL_KWARGS = {"autocommit": True, "prepare_threshold": 0}


async def open_checkpointer() -> tuple[AsyncConnectionPool, AsyncPostgresSaver]:
    """Open the psycopg3 pool, build the saver, run setup(). Raises on failure."""
    dsn = os.environ["POSTGRES_DSN"]
    pool = AsyncConnectionPool(
        conninfo=dsn,
        max_size=int(os.environ.get("CHECKPOINTER_POOL_MAX", "5")),
        kwargs=_POOL_KWARGS,
        open=False,
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    logger.info("checkpointer: AsyncPostgresSaver connected")
    return pool, saver


async def close_checkpointer(pool: AsyncConnectionPool) -> None:
    """Close the psycopg3 pool. Idempotent if the pool is already closed."""
    try:
        await pool.close()
    except Exception as e:
        logger.warning("checkpointer: pool close error: %s", e)
