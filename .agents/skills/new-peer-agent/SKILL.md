---
name: new-peer-agent
description: Use when the user runs /new-peer-agent or asks to create a new domain peer agent in this repository.
disable-model-invocation: true
---

# new-peer-agent

Scaffold a new peer agent on the foundation (ports & adapters). The reference implementation is
`agents/nutrition/`; read it first and copy its structure, not its domain logic.

## Usage

`/new-peer-agent <name>` — short, lowercase, no spaces. Ask for a name if none is given.

## Steps

1. **Discover ports in use**: `rg -o '"80[0-9]{2}:80[0-9]{2}"' docker-compose.yml | sort -u`;
   take the lowest free port in 8001–8099.
2. **Skill ids**: add a class `<Name>` with `Final` constants to `shared/src/shared/skill_ids.py`
   and a matching `Literal` alias.
3. **Package** `agents/<name>/`:
   ```
   pyproject.toml      # name "agent-<name>", hatchling, packages = ["src/<name>"], depends on "shared"
   Dockerfile          # copy agents/nutrition/Dockerfile; change package, module and port
   src/<name>/
     domain/           # pure dataclasses and functions (no shared/sqlalchemy/a2a)
     application/      # use cases: async callables (SkillRequest, consult) -> SkillResult;
                       # ports.py with repository Protocols; prompts; pydantic LLM schemas
     adapters/db.py    # SQL repositories over shared.schema tables + <name>_uow(engine)
     adapters/a2a/card.py   # SKILLS, PEER_SKILLS, build_agent_card(url)
     settings.py       # <Name>Settings(BaseServiceSettings)
     composition.py    # build_runtime(settings, *, overrides...) -> runtime with SkillExecutor
     main.py           # create_app(runtime=None)
     serve.py          # init_telemetry("agent-<name>") first, then app = create_app()
     testing.py        # in-memory repositories
   tests/unit/ tests/contract/ tests/integration/ tests/evals/
   ```
4. **Schema**: if the agent needs tables, add them to `shared/src/shared/schema/tables.py`, write
   a domain root with `down_revision = None`, `branch_labels = ("<name>",)` and
   `depends_on = "c0001_initial"`; later revisions link within that domain. Enable and
   force RLS for per-user tables. See `deploy/postgres/README.md`.
5. **Contracts**: repository contract tests run against both the in-memory and SQL backends
   (copy `agents/nutrition/tests/contract/test_repositories.py`); add the package to the
   import-linter contracts, mypy `files` / `mypy_path` and pytest `testpaths` in the root `pyproject.toml`.
6. **Compose**: add `agent-<name>` with `DATABASE__DSN` on role `app_rw`, a healthcheck on
   `/health`, wait for successful `migrate`, and add it to the orchestrator's `depends_on` and `AGENT_URLS`.
7. **Verify**: `make lint && make test && make test-integration`, then
   `docker compose up --build -d agent-<name>` and
   `curl localhost:<port>/.well-known/agent-card.json`.

## Things that bite

- `serve.py` must call `init_telemetry` before importing anything else.
- Card skill ids, `shared.skill_ids` and the handler keys must be the same set (contract test).
- Never read `os.environ` outside `shared.config`; never import legacy `shared` modules from new
  code — wrap them in an adapter under `shared/src/shared/adapters/` if you must.
- Create package namespace files before `make sync` or enabling import contracts; keep
  DTOs that compose shared domain values in `application/models.py`.
- Composition calls `configure_logging(settings.telemetry)` before adapter operations;
  INFO-and-above logs contain neither user text nor LLM output.
- Set every UoW tenant explicitly. The health-log dedup key is
  `(user_id, source, type, recorded_at)`; chat collisions shift the UTC instant by 1 microsecond.
- Re-lock after dependency edits before a frozen Docker build. If using `--extra claude`,
  declare the selected agent's extra delegating to `shared[claude]` as nutrition does.
- Model-failure results set `SkillResult.failed=True`; valid empty extraction is a completed
  clarification. Keep terminal statuses and artifact order covered by A2A contract tests.
