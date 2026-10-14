.PHONY: sync fmt lint test test-slow test-integration evals migrate sync-smoke sync-reencrypt

sync:
	uv sync --all-packages --all-extras

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy
	@if grep -q '^\[tool.importlinter\]' pyproject.toml; then uv run lint-imports; fi

test:
	uv run pytest -m "not integration and not evals and not slow" -q

test-slow:
	uv run pytest -m slow -q

test-integration:
	uv run pytest -m integration -q

evals:
	@if [ -f .env ]; then \
		uv run --env-file .env pytest -m evals -q; \
	else \
		uv run pytest -m evals -q; \
	fi

migrate:
	uv run python -m shared.schema

sync-smoke:
	@test -n "$(USER_ID)" || { echo "usage: make sync-smoke USER_ID=<uuid> [SERVICE=garmin|yazio] [DRY_RUN=1]"; exit 2; }
	docker compose run --rm sync-service python -m sync.smoke --user $(USER_ID) \
		$(if $(SERVICE),--service $(SERVICE),) $(if $(DRY_RUN),--dry-run,)

sync-reencrypt:
	docker compose run --rm sync-service python -m sync.reencrypt
