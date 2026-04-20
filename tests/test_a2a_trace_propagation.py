"""Live-stack smoke: orchestrator → peer-agent call produces a single-trace tree.

Requires full docker-compose stack up + LANGFUSE_PUBLIC_KEY/SECRET_KEY configured.
Skipped in CI; local dev only.
"""
import os
import time
import uuid
import httpx
import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("LANGFUSE_PUBLIC_KEY"),
    reason="Requires live langfuse; set LANGFUSE_PUBLIC_KEY to enable"
)


def test_chat_stream_produces_single_trace_visible_in_langfuse():
    thread_id = f"pytest-a2a-{uuid.uuid4().hex[:8]}"
    r = httpx.post(
        "http://localhost:8000/chat/stream",
        json={
            "threadId": thread_id,
            "messages": [{"role": "user", "content": "what did I eat yesterday?"}],
        },
        timeout=60,
    )
    assert r.status_code == 200

    time.sleep(8)

    pub = os.environ["LANGFUSE_PUBLIC_KEY"]
    sec = os.environ["LANGFUSE_SECRET_KEY"]
    resp = httpx.get(
        f"http://localhost:3100/api/public/traces?sessionId={thread_id}",
        auth=(pub, sec),
        timeout=10,
    )
    assert resp.status_code == 200
    data = resp.json()
    traces = data.get("data", [])
    assert len(traces) >= 1, f"No trace for session {thread_id}"

    trace_id = traces[0]["id"]
    full = httpx.get(
        f"http://localhost:3100/api/public/traces/{trace_id}",
        auth=(pub, sec),
        timeout=10,
    ).json()

    span_names = [obs.get("name", "") for obs in full.get("observations", [])]
    assert any("/chat/stream" in n for n in span_names), f"no /chat/stream span: {span_names}"
    assert any("agent" in n.lower() or "a2a" in n.lower() for n in span_names), f"no agent span: {span_names}"
