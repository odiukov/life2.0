import json

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


def events(response):
    assert response.status_code == 200, response.text
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


def proposal_script(models):
    models.script(
        AIMessage(
            "",
            tool_calls=[
                {
                    "name": "ask_home_agent",
                    "args": {"message": "Turn off lamp", "skill": "home.ask"},
                    "id": "1",
                }
            ],
        ),
        AIMessage("Confirm in the app."),
    )


async def test_full_chat_confirmation_restore_and_atomic_close(live, clean_db):
    task = await live.open("home")
    proposal_script(live.models)
    stream = events(
        await live.http.post(
            f"/tasks/{task}/messages",
            data={"text": "Turn off lamp", "timezone": "Europe/Kyiv"},
            headers=live.headers,
        )
    )
    assert {"type": "AgentRouted", "primary": "home"} in stream
    assert stream[-1]["type"] == "RunFinished"
    assert not [e for e in stream if e["type"] == "RunError"]
    action = next(e["actionId"] for e in stream if e["type"] == "ActionProposed")
    restored = (await live.http.get(f"/tasks/{task}", headers=live.headers)).json()
    assert len(restored["messages"]) == 2
    assert restored["pending_action"]["id"] == action
    assert restored["messages"][-1]["action"]["status"] == "pending"
    assert "household_id" not in restored["task"]
    for _ in range(2):
        resolved = await live.http.post(
            f"/tasks/{task}/actions/{action}", json={"decision": "confirm"}, headers=live.headers
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "applied"
    assert live.assistant.calls == [("HassTurnOff", {"name": "Lamp"})]
    restored = (await live.http.get(f"/tasks/{task}", headers=live.headers)).json()
    assert restored["messages"][-1]["action"]["status"] == "applied"
    assert restored["pending_action"] is None
    assert (await live.http.delete(f"/tasks/{task}", headers=live.headers)).status_code == 204
    assert (await live.http.get(f"/tasks/{task}", headers=live.headers)).status_code == 404
    admin = create_async_engine(clean_db.admin)
    try:
        async with admin.connect() as conn:
            for table in (
                "chat_tasks",
                "chat_messages",
                "pending_actions",
                "checkpoints",
                "checkpoint_blobs",
                "checkpoint_writes",
            ):
                where = (
                    "thread_id = :key"
                    if table.startswith("checkpoint")
                    else (
                        "id = CAST(:id AS uuid)"
                        if table == "chat_tasks"
                        else "task_id = CAST(:id AS uuid)"
                    )
                )
                assert (
                    await conn.execute(
                        text(f"SELECT count(*) FROM {table} WHERE {where}"),
                        {"key": f"{live.user}:{task}", "id": task},
                    )
                ).scalar_one() == 0
    finally:
        await admin.dispose()


async def test_typed_confirmation_and_reject_skip_model(live):
    task = await live.open("home")
    for decision, status in [("no", "rejected"), ("yes", "applied")]:
        proposal_script(live.models)
        events(
            await live.http.post(
                f"/tasks/{task}/messages", data={"text": "Turn off lamp"}, headers=live.headers
            )
        )
        live.models.script(AIMessage("Model must not be called"))
        result = events(
            await live.http.post(
                f"/tasks/{task}/messages", data={"text": decision}, headers=live.headers
            )
        )
        assert next(e["status"] for e in result if e["type"] == "ActionResolved") == status
        assert "Model must not be called" not in str(result)
    assert len(live.assistant.calls) == 1
