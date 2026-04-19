#!/usr/bin/env bash
# Two-step smoke for Home Assistant MCP integration.
#
# 1. Probe HA REST /api/ with Bearer — proves token works.
# 2. Instantiate MultiServerMCPClient locally from .venv/bin/python and
#    list discovered HA tools — proves SSE endpoint is reachable and the
#    orchestrator's MCP config shape is correct.
#
# Requires: HA_BASE_URL and HA_TOKEN exported in the shell (source .env
# or pass inline: HA_BASE_URL=... HA_TOKEN=... bash scripts/smoke-ha-mcp.sh).

set -euo pipefail

: "${HA_BASE_URL:?HA_BASE_URL must be set}"
: "${HA_TOKEN:?HA_TOKEN must be set}"

HA_BASE_URL="${HA_BASE_URL%/}"
export HA_BASE_URL HA_TOKEN

echo "== Step 1: REST /api/ with Bearer =="
curl -fsS -H "Authorization: Bearer $HA_TOKEN" "$HA_BASE_URL/api/" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d, indent=2))"

echo
echo "== Step 2: MCP tool discovery =="
.venv/bin/python - <<'PY'
import asyncio, os

async def main():
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_mcp_adapters.tools import load_mcp_tools
    base = os.environ["HA_BASE_URL"].rstrip("/")
    client = MultiServerMCPClient({
        "home-assistant": {
            "url": f"{base}/mcp_server/sse",
            "transport": "sse",
            "headers": {"Authorization": f"Bearer {os.environ['HA_TOKEN']}"},
        }
    })
    async with client.session("home-assistant") as session:
        tools = await load_mcp_tools(session)
        print(f"discovered {len(tools)} tools:")
        for t in tools:
            print(f"  - {t.name}")

asyncio.run(main())
PY
