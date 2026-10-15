import asyncio
import json

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .test_task_routes import events, proposal_script

pytestmark = pytest.mark.integration


async def test_foreign_task_and_action_are_invisible(live, clean_db):
    task = await live.open("home")
    proposal_script(live.models)
    result = events(
        await live.http.post(
            f"/tasks/{task}/messages", data={"text": "Turn off lamp"}, headers=live.headers
        )
    )
    action = next(e["actionId"] for e in result if e["type"] == "ActionProposed")
    headers = {"X-User-Id": live.other}
    for method, path, kwargs in [
        ("GET", f"/tasks/{task}", {}),
        ("PATCH", f"/tasks/{task}", {"json": {"lead_agent": "home"}}),
        ("DELETE", f"/tasks/{task}", {}),
        ("POST", f"/tasks/{task}/messages", {"data": {"text": "hello"}}),
        ("POST", f"/tasks/{task}/actions/{action}", {"json": {"decision": "confirm"}}),
    ]:
        response = await live.http.request(method, path, headers=headers, **kwargs)
        assert response.status_code == 404, response.text
    rw = create_async_engine(clean_db.rw)
    try:
        async with rw.begin() as conn:
            await conn.execute(
                text("SELECT set_config('app.user_id', :u, true)"), {"u": live.other}
            )
            for table in (
                "chat_tasks",
                "chat_messages",
                "pending_actions",
                "checkpoints",
                "checkpoint_blobs",
                "checkpoint_writes",
            ):
                assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
    finally:
        await rw.dispose()
    assert live.assistant.calls == []


async def test_image_bytes_never_persist_in_checkpoint_or_transcript(live, clean_db):
    task = await live.open()
    marker = b"SECRET-IMAGE-BYTES"
    photo = b"\xff\xd8\xff" + marker
    events(
        await live.http.post(
            f"/tasks/{task}/messages",
            data={"text": "Describe photo"},
            files={"attachments": ("milk.jpg", photo, "image/jpeg")},
            headers=live.headers,
        )
    )
    restored = (await live.http.get(f"/tasks/{task}", headers=live.headers)).json()
    assert restored["messages"][0]["attachments"] == [
        {"kind": "image", "name": "milk.jpg", "mime": "image/jpeg", "size": len(photo)}
    ]
    assert marker.decode() not in json.dumps(restored)
    admin = create_async_engine(clean_db.admin)
    try:
        async with admin.connect() as conn:
            for table in ("checkpoint_blobs", "checkpoint_writes", "checkpoints", "chat_messages"):
                rows = (await conn.execute(text(f"SELECT * FROM {table}"))).all()
                assert rows
                for row in rows:
                    for value in row:
                        assert marker not in (
                            bytes(value)
                            if isinstance(value, (bytes, bytearray, memoryview))
                            else str(value).encode()
                        )
    finally:
        await admin.dispose()


async def test_concurrent_posts_only_one_runs(live):
    task = await live.open()
    live.models.model.sleep = 0.5
    live.models.script(AIMessage("Answer"))
    first, second = await asyncio.gather(
        *[
            live.http.post(f"/tasks/{task}/messages", data={"text": "hello"}, headers=live.headers)
            for _ in range(2)
        ]
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    denied = first if first.status_code == 409 else second
    assert denied.json()["detail"] == "task_busy"
    restored = (await live.http.get(f"/tasks/{task}", headers=live.headers)).json()
    assert len(restored["messages"]) == 2


async def test_checkpoint_and_task_deletion_roll_back_together(live, clean_db):
    from uuid import UUID

    from orchestrator.adapters.db import SqlChatTasks

    task = await live.open()
    events(
        await live.http.post(
            f"/tasks/{task}/messages", data={"text": "hello"}, headers=live.headers
        )
    )
    rw = create_async_engine(clean_db.rw)
    try:
        async with rw.connect() as conn:
            transaction = await conn.begin()
            await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": live.user})
            assert await SqlChatTasks(conn).delete(UUID(live.user), UUID(task))
            assert (await conn.execute(text("SELECT count(*) FROM checkpoints"))).scalar_one() == 0
            await transaction.rollback()
        async with rw.begin() as conn:
            await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": live.user})
            assert (await conn.execute(text("SELECT count(*) FROM chat_tasks"))).scalar_one() == 1
            assert (await conn.execute(text("SELECT count(*) FROM checkpoints"))).scalar_one() > 0
            assert (
                await conn.execute(text("SELECT count(*) FROM chat_messages"))
            ).scalar_one() == 2
    finally:
        await rw.dispose()


async def test_consent_defaults_false_is_tenant_scoped_and_expires(live, clean_db, monkeypatch):
    from uuid import UUID

    from orchestrator.adapters.db import SqlConsentLookup

    rw = create_async_engine(clean_db.rw)
    lookup = SqlConsentLookup(rw)
    user, other = UUID(live.user), UUID(live.other)
    now = [1000.0]
    monkeypatch.setattr("orchestrator.adapters.db.monotonic", lambda: now[0])
    try:
        assert not await lookup.bodies_ok(user)
        async with rw.begin() as conn:
            await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": live.user})
            await conn.execute(
                text(
                    "INSERT INTO telemetry_consent (user_id, bodies_ok) VALUES (CAST(:u AS uuid), true)"
                ),
                {"u": live.user},
            )
        assert not await lookup.bodies_ok(user)
        now[0] += 301
        assert await lookup.bodies_ok(user)
        assert not await lookup.bodies_ok(other)
    finally:
        await rw.dispose()
