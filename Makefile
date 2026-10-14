.PHONY: sync fmt lint test test-slow test-integration evals migrate

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
	uv run pytest -m evals -q

migrate:
	uv run python -m shared.schema
