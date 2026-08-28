import pytest
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, patch

USER = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_upsert_memory_calls_embed_and_qdrant_with_payload():
    client = MagicMock()
    missing_collections = MagicMock()
    missing_collections.collections = []
    client.get_collections = AsyncMock(return_value=missing_collections)
    client.create_collection = AsyncMock()
    client.create_payload_index = AsyncMock()
    client.upsert = AsyncMock()

    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock(return_value=[0.0] * 768)):
        from shared.vector import upsert_memory
        await upsert_memory(
            user_id=USER, agent_id="sleep", id_="abc", text="плохо спал",
            metadata={"skill": "log_sleep"},
        )

    client.create_collection.assert_awaited_once()
    # One index per field (agent_id + user_id).
    assert client.create_payload_index.await_count == 2
    assert client.upsert.await_count == 1
    kwargs = client.upsert.await_args.kwargs
    assert kwargs["collection_name"] == "health_memories"
    point = kwargs["points"][0]
    assert point.payload["user_id"] == str(USER)
    assert point.payload["agent_id"] == "sleep"
    assert point.payload["text"] == "плохо спал"
    assert point.payload["source"] == "agent"
    assert point.payload["skill"] == "log_sleep"
    assert len(point.vector) == 768


@pytest.mark.asyncio
async def test_search_memories_without_agent_ids_passes_only_user_filter():
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    client = MagicMock()
    present = MagicMock()
    present.collections = [MagicMock()]
    present.collections[0].name = "health_memories"
    client.get_collections = AsyncMock(return_value=present)
    client.query_points = AsyncMock(return_value=MagicMock(points=[
        MagicMock(payload={"text": "m1", "agent_id": "sleep"}),
    ]))

    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock(return_value=[0.0] * 768)):
        from shared.vector import search_memories
        out = await search_memories(USER, "query", limit=3)

    assert out == [{"text": "m1", "agent_id": "sleep"}]
    kwargs = client.query_points.await_args.kwargs
    assert kwargs["collection_name"] == "health_memories"
    assert kwargs["limit"] == 3
    qf = kwargs["query_filter"]
    assert isinstance(qf, Filter)
    assert len(qf.must) == 1
    cond = qf.must[0]
    assert isinstance(cond, FieldCondition)
    assert cond.key == "user_id"
    assert isinstance(cond.match, MatchValue)
    assert cond.match.value == str(USER)


@pytest.mark.asyncio
async def test_search_memories_with_agent_ids_builds_match_any_filter():
    from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue
    client = MagicMock()
    present = MagicMock()
    present.collections = [MagicMock()]
    present.collections[0].name = "health_memories"
    client.get_collections = AsyncMock(return_value=present)
    client.query_points = AsyncMock(return_value=MagicMock(points=[]))

    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock(return_value=[0.0] * 768)):
        from shared.vector import search_memories
        await search_memories(USER, "q", limit=5, agent_ids=["sleep", "nutrition"])

    qf = client.query_points.await_args.kwargs["query_filter"]
    assert isinstance(qf, Filter)
    assert len(qf.must) == 2
    user_cond, agent_cond = qf.must
    assert user_cond.key == "user_id"
    assert isinstance(user_cond.match, MatchValue)
    assert user_cond.match.value == str(USER)
    assert agent_cond.key == "agent_id"
    assert isinstance(agent_cond.match, MatchAny)
    assert set(agent_cond.match.any) == {"sleep", "nutrition"}


@pytest.mark.asyncio
async def test_upsert_memory_swallows_embedding_error():
    from shared.embeddings import EmbeddingError
    client = MagicMock()
    client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    client.create_collection = AsyncMock()
    client.create_payload_index = AsyncMock()
    client.upsert = AsyncMock()

    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock(side_effect=EmbeddingError("boom"))):
        from shared.vector import upsert_memory
        await upsert_memory(user_id=USER, agent_id="sleep", id_="abc", text="t", metadata={})

    client.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_memories_swallows_embedding_error_returns_empty():
    from shared.embeddings import EmbeddingError
    client = MagicMock()
    present = MagicMock()
    present.collections = [MagicMock()]
    present.collections[0].name = "health_memories"
    client.get_collections = AsyncMock(return_value=present)

    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock(side_effect=EmbeddingError("boom"))):
        from shared.vector import search_memories
        out = await search_memories(USER, "q")

    assert out == []


@pytest.mark.asyncio
async def test_upsert_memory_skips_empty_text():
    client = MagicMock()
    client.upsert = AsyncMock()
    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock()) as emb:
        from shared.vector import upsert_memory
        await upsert_memory(user_id=USER, agent_id="sleep", id_="x", text="   ", metadata={})
    emb.assert_not_called()
    client.upsert.assert_not_called()
