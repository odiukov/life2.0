"""VectorMemory over legacy Qdrant helpers (QDRANT_HOST/PORT and GEMINI_API_KEY).

The transitional helper does not consume the typed QDRANT_URL setting.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from uuid import UUID

from shared import vector as legacy_vector
from shared.observability.logging import get_logger
from shared.ports.vector_memory import Memory

_RESERVED = {"text", "agent_id", "user_id"}
logger = get_logger(__name__)


class QdrantVectorMemory:
    async def upsert(
        self, *, user_id: UUID, agent: str, key: str, text: str, metadata: Mapping[str, str]
    ) -> None:
        # Legacy point ids are global: encode the complete logical identity.
        identity = json.dumps([str(user_id), agent, key], separators=(",", ":"))
        try:
            await legacy_vector.upsert_memory(
                user_id=user_id,
                agent_id=agent,
                id_=identity,
                text=text,
                metadata={name: value for name, value in metadata.items() if name not in _RESERVED},
            )
        except Exception as exc:
            logger.warning("vector_upsert_failed", error_type=type(exc).__name__)

    async def search(
        self, *, user_id: UUID, query: str, limit: int, agents: Sequence[str] | None = None
    ) -> list[Memory]:
        try:
            payloads = await legacy_vector.search_memories(
                user_id, query, limit=limit, agent_ids=list(agents) if agents else None
            )
        except Exception as exc:
            logger.warning("vector_search_failed", error_type=type(exc).__name__)
            return []
        return [
            Memory(
                text=str(payload.get("text", "")),
                agent=str(payload.get("agent_id", "")),
                metadata={
                    name: str(value) for name, value in payload.items() if name not in _RESERVED
                },
            )
            for payload in payloads
        ]
