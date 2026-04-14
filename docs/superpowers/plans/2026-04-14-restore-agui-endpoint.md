# Restore /agui endpoint + copilotkit-runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the frontend↔backend chat chain by mounting an AG-UI endpoint on the orchestrator and adding a Node `copilotkit-runtime` container that bridges the CopilotKit v1.8 frontend to it.

**Architecture:** Browser → nginx → `copilotkit-runtime:4000` (Node) → `orchestrator:8000/agui` (FastAPI + `ag_ui_langgraph`) → existing `create_health_agent()` LangGraph ReAct graph.

**Tech Stack:** Python FastAPI, `ag-ui-langgraph`, Node 20, `@copilotkit/runtime@^1.8`, `@ag-ui/client`, Express, Docker Compose, nginx.

**Spec:** `docs/superpowers/specs/2026-04-14-restore-agui-endpoint-design.md`

---

## File Structure

**Create:**
- `copilotkit-runtime/package.json`
- `copilotkit-runtime/server.js`
- `copilotkit-runtime/Dockerfile`
- `copilotkit-runtime/.dockerignore`
- `tests/test_orchestrator_agui_route.py`

**Modify:**
- `orchestrator/app/main.py` — swap Python CopilotKit SDK mount for `/agui` mount
- `orchestrator/requirements.txt` — drop `copilotkit`, add `ag-ui-langgraph`
- `docker-compose.yml` — add `copilotkit-runtime` service, update `agui-frontend.depends_on`
- `agui-frontend/nginx.conf` — repoint `/copilotkit` proxies at `copilotkit-runtime:4000`

---

## Task 1: Pivot orchestrator from `/copilotkit` (Python SDK) to `/agui` (ag_ui_langgraph)

**Files:**
- Modify: `orchestrator/app/main.py` (lines 12-14, 47-73)
- Modify: `orchestrator/requirements.txt`
- Create: `tests/test_orchestrator_agui_route.py`

- [ ] **Step 1: Write failing test for `/agui` route registration**

Create `tests/test_orchestrator_agui_route.py`:

```python
from orchestrator.app.main import app


def _route_paths() -> set[str]:
    return {getattr(r, "path", None) for r in app.routes}


def test_agui_route_registered():
    paths = _route_paths()
    agui_paths = {p for p in paths if p and p.startswith("/agui")}
    assert agui_paths, f"no /agui route registered; got {sorted(p for p in paths if p)}"


def test_old_copilotkit_route_removed():
    paths = _route_paths()
    copilotkit_paths = {p for p in paths if p and p.startswith("/copilotkit")}
    assert not copilotkit_paths, f"/copilotkit route should be gone; got {copilotkit_paths}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator_agui_route.py -v`
Expected: FAIL — `test_agui_route_registered` fails (no `/agui` path) and `test_old_copilotkit_route_removed` fails (existing `/copilotkit` still mounted), OR import error if `ag_ui_langgraph` missing (go to Step 3).

- [ ] **Step 3: Swap `copilotkit` for `ag-ui-langgraph` in requirements**

Edit `orchestrator/requirements.txt`. Remove the line `copilotkit>=0.1.39,<0.2`. Add `ag-ui-langgraph`. Final file:

```
fastapi>=0.111
uvicorn[standard]>=0.29
httpx>=0.27
asyncpg>=0.29
ag-ui-langgraph
langchain-anthropic>=0.3
langchain-openai>=0.3
```

- [ ] **Step 4: Install new dep locally so the test can import**

Run: `pip install ag-ui-langgraph && pip uninstall -y copilotkit`
Expected: `ag-ui-langgraph` installed successfully.

If `ag-ui-langgraph` fails to resolve against the current `langgraph`/`langchain-core` pins: try `pip install "ag-ui-langgraph<1.0"`. Record the resolved version and pin it explicitly in `orchestrator/requirements.txt` (e.g. `ag-ui-langgraph==0.0.X`).

- [ ] **Step 5: Rewrite orchestrator mount in `orchestrator/app/main.py`**

Replace lines 12-14 (imports):

```python
# DELETE these three lines:
# from copilotkit import CopilotKitRemoteEndpoint
# from copilotkit.langgraph_agent import LangGraphAgent as _CopilotKitLangGraphAgent
# from copilotkit.integrations.fastapi import add_fastapi_endpoint

# ADD:
from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
```

Replace lines 47-73 (the whole `# CopilotKit SDK — LangGraph agent required by CopilotKit v1.8` block from the comment down through `add_fastapi_endpoint(app, _copilotkit_sdk, "/copilotkit")`) with:

```python
# ---------------------------------------------------------------------------
# AG-UI endpoint — consumed by the Node copilotkit-runtime container which
# bridges CopilotKit v1.8 frontend → AG-UI → LangGraph.
# ---------------------------------------------------------------------------

add_langgraph_fastapi_endpoint(
    app,
    LangGraphAgent(
        name="default",
        description="Personal health assistant with access to sleep, workout, and nutrition data",
        graph=create_health_agent(),
    ),
    path="/agui",
)
```

Leave every other route (`/chat`, `/chat/stream`, `/stats`, `/health-summary`, `/agents`, `/briefing`, `/activity`, `/health`) untouched.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_orchestrator_agui_route.py -v`
Expected: PASS (both tests).

- [ ] **Step 7: Run full orchestrator test suite to catch regressions**

Run: `pytest tests/test_orchestrator_stats.py tests/test_orchestrator_routing.py tests/test_orchestrator_stream.py tests/test_orchestrator_agui_route.py -v`
Expected: All pass. If a previous `test_copilotkit_endpoint*.py` file exists and fails, delete it (it was already removed in commit `fa9ba314` per git log; verify with `ls tests/ | grep -i copilotkit`).

- [ ] **Step 8: Commit**

```bash
git add orchestrator/app/main.py orchestrator/requirements.txt tests/test_orchestrator_agui_route.py
git commit -m "$(cat <<'EOF'
feat: mount /agui endpoint via ag_ui_langgraph, drop copilotkit Python SDK

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create the `copilotkit-runtime` Node service

**Files:**
- Create: `copilotkit-runtime/package.json`
- Create: `copilotkit-runtime/server.js`
- Create: `copilotkit-runtime/Dockerfile`
- Create: `copilotkit-runtime/.dockerignore`

- [ ] **Step 1: Create `copilotkit-runtime/package.json`**

```json
{
  "name": "copilotkit-runtime",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "node server.js"
  },
  "dependencies": {
    "@copilotkit/runtime": "^1.8.0",
    "@ag-ui/client": "*",
    "express": "^4.19.2",
    "cors": "^2.8.5"
  }
}
```

- [ ] **Step 2: Generate `package-lock.json` and verify deps resolve**

Run:
```bash
cd copilotkit-runtime && npm install && cd ..
```
Expected: `node_modules/` and `package-lock.json` created, no ERESOLVE errors.

If `@ag-ui/client` resolves to a version incompatible with `@copilotkit/runtime@1.8`, try `@ag-ui/client@^0.0` then `^0.1`. Record the pinned version in `package.json`.

- [ ] **Step 3: Create `copilotkit-runtime/server.js`**

```js
import express from "express";
import cors from "cors";
import { CopilotRuntime, copilotRuntimeNodeHttpEndpoint } from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";

const PORT = 4000;
const ORCHESTRATOR_AGUI_URL =
  process.env.ORCHESTRATOR_AGUI_URL || "http://orchestrator:8000/agui";

const runtime = new CopilotRuntime({
  agents: {
    default: new HttpAgent({ url: ORCHESTRATOR_AGUI_URL }),
  },
});

const app = express();
app.use(cors());

app.get("/health", (_req, res) => res.json({ status: "ok" }));

app.use("/copilotkit", (req, res, next) =>
  copilotRuntimeNodeHttpEndpoint({
    endpoint: "/copilotkit",
    runtime,
  })(req, res, next)
);

app.listen(PORT, () => {
  console.log(`copilotkit-runtime listening on :${PORT}, bridging to ${ORCHESTRATOR_AGUI_URL}`);
});
```

- [ ] **Step 4: Smoke-test the server locally (no Docker)**

Run:
```bash
cd copilotkit-runtime && node server.js &
sleep 2
curl -sf http://localhost:4000/health
kill %1
cd ..
```
Expected: `{"status":"ok"}`. If import errors appear, check the actual export names in `node_modules/@copilotkit/runtime/dist/` (README of the installed version is authoritative). Adjust the `import { ... }` line to match and retry.

- [ ] **Step 5: Create `copilotkit-runtime/Dockerfile`**

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY server.js ./
EXPOSE 4000
CMD ["node", "server.js"]
```

- [ ] **Step 6: Create `copilotkit-runtime/.dockerignore`**

```
node_modules
npm-debug.log
.env
.env.*
```

- [ ] **Step 7: Build the image to confirm Dockerfile is valid**

Run: `docker build -t copilotkit-runtime:test copilotkit-runtime/`
Expected: Build succeeds. No need to keep the image tagged — verification only.

- [ ] **Step 8: Commit**

```bash
git add copilotkit-runtime/
git commit -m "$(cat <<'EOF'
feat: add copilotkit-runtime Node bridge for CopilotKit v1.8 → AG-UI

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Wire `copilotkit-runtime` into docker-compose

**Files:**
- Modify: `docker-compose.yml` (add service, update agui-frontend deps)

- [ ] **Step 1: Add `copilotkit-runtime` service and update `agui-frontend`**

Edit `docker-compose.yml`. Insert this service block after the `agui-frontend` block (between `agui-frontend:` and `sync-service:`):

```yaml
  copilotkit-runtime:
    build: ./copilotkit-runtime
    environment:
      ORCHESTRATOR_AGUI_URL: http://orchestrator:8000/agui
    depends_on:
      orchestrator:
        condition: service_started
    restart: unless-stopped
```

Then update the existing `agui-frontend` block so its `depends_on` waits on the runtime too. Change:

```yaml
  agui-frontend:
    build:
      context: ./agui-frontend
    ports:
      - "3000:80"
    depends_on:
      orchestrator:
        condition: service_started
    restart: unless-stopped
```

to:

```yaml
  agui-frontend:
    build:
      context: ./agui-frontend
    ports:
      - "3000:80"
    depends_on:
      orchestrator:
        condition: service_started
      copilotkit-runtime:
        condition: service_started
    restart: unless-stopped
```

- [ ] **Step 2: Validate compose file syntax**

Run: `docker compose config >/dev/null`
Expected: No output (validation passes). If errors, fix the YAML indentation.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "$(cat <<'EOF'
feat: add copilotkit-runtime service to docker-compose

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Repoint nginx `/copilotkit` at the Node runtime

**Files:**
- Modify: `agui-frontend/nginx.conf` (lines 39-57)

- [ ] **Step 1: Update both `/copilotkit` locations**

Edit `agui-frontend/nginx.conf`. Replace lines 39-57 (the `location = /copilotkit` and `location /copilotkit/` blocks) with:

```nginx
    location = /copilotkit {
        proxy_pass http://copilotkit-runtime:4000;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /copilotkit/ {
        proxy_pass http://copilotkit-runtime:4000;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        proxy_set_header X-Real-IP $remote_addr;
    }
```

Leave all other `location` blocks unchanged.

- [ ] **Step 2: Validate nginx config by building the frontend image**

Run: `docker build -t agui-frontend:test agui-frontend/`
Expected: Build succeeds. nginx syntax is checked at container start, not build — next task verifies runtime.

- [ ] **Step 3: Commit**

```bash
git add agui-frontend/nginx.conf
git commit -m "$(cat <<'EOF'
fix: proxy /copilotkit through copilotkit-runtime instead of orchestrator

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: End-to-end verification

**Files:** none (manual verification)

- [ ] **Step 1: Refresh Claude auth and start the stack**

Run:
```bash
./scripts/export-auth.sh
docker compose down
docker compose up --build -d
```
Expected: All services reach `Up` / `healthy` within ~60 s.

- [ ] **Step 2: Confirm all containers are up**

Run: `docker compose ps`
Expected output contains a row for `copilotkit-runtime` with state `Up`, plus all previously existing services healthy.

- [ ] **Step 3: Verify runtime reachability from inside the compose network**

Run:
```bash
docker compose exec agui-frontend wget -qO- http://copilotkit-runtime:4000/health
```
Expected: `{"status":"ok"}`.

- [ ] **Step 4: Verify the orchestrator `/agui` endpoint is live**

Run:
```bash
docker compose exec copilotkit-runtime wget -qO- --server-response \
  --post-data='{}' --header='Content-Type: application/json' \
  http://orchestrator:8000/agui 2>&1 | head -20
```
Expected: A response status — NOT `404 Not Found`. A 4xx about missing fields or a 200 SSE stream both indicate the path is registered.

- [ ] **Step 5: Browser smoke test**

Open http://localhost:3000 in a browser. In the chat panel on the Dashboard page, type: `how did I sleep last night?`
Expected:
  - Response streams into the chat (not stuck, no "INCOMPLETE_STREAM" error).
  - `docker compose logs -f orchestrator` shows a POST to `http://agent-sleep:8001/tasks`.

- [ ] **Step 6: Verify frontend action routing still works**

In the same chat, type: `highlight the sleep agent`
Expected: The app navigates to the Agents tab with the sleep card visually highlighted (handler defined in `agui-frontend/src/pages/DashboardPage.tsx:33-45`).

- [ ] **Step 7: Log scan**

Run: `docker compose logs --tail=100 orchestrator copilotkit-runtime agui-frontend | grep -iE "error|traceback|exception"`
Expected: No unexpected errors. Known-benign warnings (e.g. langgraph deprecation warnings suppressed in `health_agent.py`) are fine.

- [ ] **Step 8: Update memory — mark TODO complete**

Edit `/Users/oleksandr/.claude/projects/-Users-oleksandr-Documents-life-agents/memory/MEMORY.md` — remove the line:

```
- [TODO: restore /agui endpoint](todo_restore_agui_endpoint.md) — Master's frontend↔backend chat chain is broken; needs AG-UI endpoint + copilotkit-runtime container restored
```

Delete the file `/Users/oleksandr/.claude/projects/-Users-oleksandr-Documents-life-agents/memory/todo_restore_agui_endpoint.md`.

No commit needed (memory files are outside the repo).

- [ ] **Step 9: Final commit marker (optional)**

If any tweaks were needed during verification (e.g. pinned `ag-ui-langgraph` version, pinned `@ag-ui/client` version), commit them now:

```bash
git status
# if changes exist:
git add -A
git commit -m "$(cat <<'EOF'
fix: pin ag-ui / copilotkit-runtime versions after e2e verification

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** All 6 spec components (backend main.py, requirements, copilotkit-runtime dir, docker-compose, nginx, frontend-unchanged) map to Tasks 1-4, with Task 5 covering the spec's Testing/verification section.
- **Risk hotspots:**
  - `ag-ui-langgraph` version resolution vs. existing `langgraph` (Task 1 Step 4 includes a fallback).
  - `@copilotkit/runtime` export names may have changed between minor versions (Task 2 Step 4 verifies by running the server; fix import names if needed).
  - `HttpAgent` constructor signature on `@ag-ui/client` may differ by version (same verification catches it).
- **No unit tests for the Node runtime** — intentional per spec ("out of scope"). Task 5 covers it end-to-end.
