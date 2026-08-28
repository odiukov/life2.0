"""Live-stack smoke: orchestrator → calendar-mcp (via streamable-http) produces
a trace tree — at minimum the outgoing httpx span to calendar-mcp.

Remote MCP server is not our code, so we only assert that the orchestrator-side
httpx call creates a span and that span is part of the same trace as /chat/stream.
"""
import os
import time
import uuid
import httpx
import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("LANGFUSE_PUBLIC_KEY"),
    reason="Requires live langfuse + MCP auth. Set LANGFUSE_PUBLIC_KEY to enable."
)


def test_calendar_mcp_invocation_produces_outgoing_httpx_span():
    thread_id = f"pytest-mcp-{uuid.uuid4().hex[:8]}"
    r = httpx.post(
        "http://localhost:8000/chat/stream",
        json={
            "threadId": thread_id,
            "messages": [{"role": "user", "content": "what's on my calendar today?"}],
        },
        timeout=60,
    )
    assert r.status_code == 200

    time.sleep(8)

    pub = os.environ["LANGFUSE_PUBLIC_KEY"]
    sec = os.environ["LANGFUSE_SECRET_KEY"]
    data = httpx.get(
        f"http://localhost:3100/api/public/traces?sessionId={thread_id}",
        auth=(pub, sec),
        timeout=10,
    ).json()
    traces = data.get("data", [])
    assert len(traces) >= 1, f"No trace for session {thread_id}"

    trace_id = traces[0]["id"]
    full = httpx.get(
        f"http://localhost:3100/api/public/traces/{trace_id}",
        auth=(pub, sec),
        timeout=10,
    ).json()

    span_names = [obs.get("name", "") for obs in full.get("observations", [])]
    assert any("HTTP" in n.upper() or "POST" in n.upper() or "mcp" in n.lower() for n in span_names), \
        f"no outgoing HTTP/MCP span: {span_names}"
