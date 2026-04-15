import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_embed_returns_vector_from_gemini_response():
    fake_response = AsyncMock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {"embedding": {"values": [0.1] * 768}}
    post = AsyncMock(return_value=fake_response)

    with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
         patch("shared.embeddings._get_client") as gc:
        gc.return_value.post = post
        from shared.embeddings import embed
        vec = await embed("hello", task_type="retrieval_document")

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

    with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
         patch("shared.embeddings._get_client") as gc:
        gc.return_value.post = post
        from shared.embeddings import embed
        await embed("q", task_type="retrieval_query")

    assert post.await_args.kwargs["json"]["taskType"] == "RETRIEVAL_QUERY"


@pytest.mark.asyncio
async def test_embed_raises_embedding_error_without_api_key():
    with patch.dict(os.environ, {}, clear=True):
        from shared.embeddings import embed, EmbeddingError
        with pytest.raises(EmbeddingError):
            await embed("hello")


@pytest.mark.asyncio
async def test_embed_wraps_http_error_in_embedding_error():
    import httpx

    def _boom():
        raise httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock(status_code=500))

    fake_response = MagicMock()
    fake_response.raise_for_status = _boom
    fake_response.json = lambda: {}
    post = AsyncMock(return_value=fake_response)

    with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
         patch("shared.embeddings._get_client") as gc:
        gc.return_value.post = post
        from shared.embeddings import embed, EmbeddingError
        with pytest.raises(EmbeddingError):
            await embed("hello")
