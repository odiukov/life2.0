#!/usr/bin/env bash
# Minimal LLM provider smoke test.
# Reads .env from repo root, builds the configured LLM via shared.llm.build_llm,
# sends a one-word ping, prints the reply and latency.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a; . ./.env; set +a
fi
if [ -f .env.auth ]; then
  set -a; . ./.env.auth; set +a
fi

python -c '
import asyncio, time, os
from shared.llm import build_llm
from langchain_core.messages import HumanMessage

async def main():
    llm = build_llm()
    t0 = time.time()
    r = await llm.ainvoke([HumanMessage("Reply with exactly one word: pong")])
    content = r.content if isinstance(r.content, str) else str(r.content)
    provider = os.environ.get("LLM_PROVIDER", "openrouter")
    print(f"[{llm._llm_type} via {provider}] {content.strip()!r} in {time.time()-t0:.2f}s")

asyncio.run(main())
'
