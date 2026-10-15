import inspect
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from shared.adapters import vector

USER = UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test__upsert_calls_embed_and_qdrant_with_payload():
    client = MagicMock()
    missing_collections = MagicMock()
    missing_collections.collections = []
    client.get_collections = AsyncMock(return_value=missing_collections)
    client.create_collection = AsyncMock()
    client.create_payload_index = AsyncMock()
    client.upsert = AsyncMock()

    with (
        patch("shared.adapters.vector._get_client", return_value=client),
        patch("shared.adapters.vector._embed", new=AsyncMock(return_value=[0.0] * 768)),
    ):
        from shared.adapters.vector import _upsert

        await _upsert(
            user_id=USER,
            agent_id="sleep",
            id_="abc",
            text="плохо спал",
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
async def test__search_without_agent_ids_passes_only_user_filter():
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    client = MagicMock()
    present = MagicMock()
    present.collections = [MagicMock()]
    present.collections[0].name = "health_memories"
    client.get_collections = AsyncMock(return_value=present)
    client.query_points = AsyncMock(
        return_value=MagicMock(
            points=[
                MagicMock(payload={"text": "m1", "agent_id": "sleep"}),
            ]
        )
    )

    with (
        patch("shared.adapters.vector._get_client", return_value=client),
        patch("shared.adapters.vector._embed", new=AsyncMock(return_value=[0.0] * 768)),
    ):
        from shared.adapters.vector import _search

        out = await _search(USER, "query", limit=3)

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
async def test__search_with_agent_ids_builds_match_any_filter():
    from qdrant_client.models import Filter, MatchAny, MatchValue

    client = MagicMock()
    present = MagicMock()
    present.collections = [MagicMock()]
    present.collections[0].name = "health_memories"
    client.get_collections = AsyncMock(return_value=present)
    client.query_points = AsyncMock(return_value=MagicMock(points=[]))

    with (
        patch("shared.adapters.vector._get_client", return_value=client),
        patch("shared.adapters.vector._embed", new=AsyncMock(return_value=[0.0] * 768)),
    ):
        from shared.adapters.vector import _search

        await _search(USER, "q", limit=5, agent_ids=["sleep", "nutrition"])

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
async def test__upsert_swallows_embedding_error():
    from shared.adapters.vector import EmbeddingError

    client = MagicMock()
    client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    client.create_collection = AsyncMock()
    client.create_payload_index = AsyncMock()
    client.upsert = AsyncMock()

    with (
        patch("shared.adapters.vector._get_client", return_value=client),
        patch("shared.adapters.vector._embed", new=AsyncMock(side_effect=EmbeddingError("boom"))),
    ):
        from shared.adapters.vector import _upsert

        await _upsert(user_id=USER, agent_id="sleep", id_="abc", text="t", metadata={})

    client.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test__search_swallows_embedding_error_returns_empty():
    from shared.adapters.vector import EmbeddingError

    client = MagicMock()
    present = MagicMock()
    present.collections = [MagicMock()]
    present.collections[0].name = "health_memories"
    client.get_collections = AsyncMock(return_value=present)

    with (
        patch("shared.adapters.vector._get_client", return_value=client),
        patch("shared.adapters.vector._embed", new=AsyncMock(side_effect=EmbeddingError("boom"))),
    ):
        from shared.adapters.vector import _search

        out = await _search(USER, "q")

    assert out == []


@pytest.mark.asyncio
async def test__upsert_skips_empty_text():
    client = MagicMock()
    client.upsert = AsyncMock()
    with (
        patch("shared.adapters.vector._get_client", return_value=client),
        patch("shared.adapters.vector._embed", new=AsyncMock()) as emb,
    ):
        from shared.adapters.vector import _upsert

        await _upsert(user_id=USER, agent_id="sleep", id_="x", text="   ", metadata={})
    emb.assert_not_called()
    client.upsert.assert_not_called()


"""Contract test: vector._search always applies a user_id filter."""


USER_A = UUID("11111111-1111-1111-1111-111111111111")


def test__upsert_signature_has_user_id_first():
    sig = inspect.signature(vector._upsert)
    params = list(sig.parameters)
    assert params[0] == "user_id", f"expected user_id first, got {params}"


def test__search_signature_has_user_id_first():
    sig = inspect.signature(vector._search)
    params = list(sig.parameters)
    assert params[0] == "user_id", f"expected user_id first, got {params}"


@pytest.mark.asyncio
async def test_embed_returns_vector_from_gemini_response():
    fake_response = AsyncMock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {"embedding": {"values": [0.1] * 768}}
    post = AsyncMock(return_value=fake_response)

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "k"}),
        patch("shared.adapters.vector._get_embedding_client") as gc,
    ):
        gc.return_value.post = post
        from shared.adapters.vector import _embed

        vec = await _embed("hello", task_type="retrieval_document")

    assert len(vec) == 768
    assert vec[0] == 0.1
    # URL contains the model
    call_url = post.await_args.args[0]
    assert "gemini-embedding-001:embedContent" in call_url
    # Body includes taskType and content
    body = post.await_args.kwargs["json"]
    assert body["content"]["parts"][0]["text"] == "hello"
    assert body["taskType"] == "RETRIEVAL_DOCUMENT"


@pytest.mark.asyncio
async def test_embed_maps_query_task_type():
    fake_response = AsyncMock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {"embedding": {"values": [0.0] * 768}}
    post = AsyncMock(return_value=fake_response)

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "k"}),
        patch("shared.adapters.vector._get_embedding_client") as gc,
    ):
        gc.return_value.post = post
        from shared.adapters.vector import _embed

        await _embed("q", task_type="retrieval_query")

    assert post.await_args.kwargs["json"]["taskType"] == "RETRIEVAL_QUERY"


@pytest.mark.asyncio
async def test_embed_raises_embedding_error_without_api_key():
    with patch.dict("os.environ", {}, clear=True):
        from shared.adapters.vector import EmbeddingError, _embed

        with pytest.raises(EmbeddingError):
            await _embed("hello")


@pytest.mark.asyncio
async def test_embed_wraps_http_error_in_embedding_error():
    import httpx

    def _boom():
        raise httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock(status_code=500))

    fake_response = MagicMock()
    fake_response.raise_for_status = _boom
    fake_response.json = lambda: {}
    post = AsyncMock(return_value=fake_response)

    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "k"}),
        patch("shared.adapters.vector._get_embedding_client") as gc,
    ):
        gc.return_value.post = post
        from shared.adapters.vector import EmbeddingError, _embed

        with pytest.raises(EmbeddingError):
            await _embed("hello")
