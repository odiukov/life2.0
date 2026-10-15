"""The generated client describes the entire public application."""

import json
from pathlib import Path

from orchestrator.openapi import openapi_document

SCHEMA = Path(__file__).resolve().parents[3] / "packages/api-client/schema/gateway.json"


def test_committed_schema_matches_the_public_app() -> None:
    expected = json.dumps(openapi_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert SCHEMA.read_text("utf-8") == expected, (
        "run: uv run python -m orchestrator.openapi packages/api-client/schema/gateway.json"
    )


def test_task_routes_are_documented() -> None:
    paths = openapi_document()["paths"]
    assert {
        "/tasks",
        "/tasks/{task_id}",
        "/tasks/{task_id}/messages",
        "/tasks/{task_id}/actions/{action_id}",
    } <= set(paths)
    assert set(paths["/tasks/{task_id}"]) >= {"get", "patch", "delete"}
