"""Gateway integration data is sealed and isolated by the caller's app_rw context."""

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
import respx
from fastapi import FastAPI
from gateway.auth.settings import AuthSettings
from gateway.composition import build_gateway, mount
from gateway.settings import GatewaySettings
from shared.adapters.secrets import AesGcmSecretBox, open_json
from shared.testing.fakes import FixedClock
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


@respx.mock
async def test_credentials_sealed_and_oauth_state_user_bound_and_expiring(clean_db):
    user, other = uuid4(), uuid4()
    now = datetime(2026, 10, 15, 12, tzinfo=UTC)
    settings = GatewaySettings.model_validate(
        {
            "database": {"dsn": clean_db.rw},
            "sync_url": "http://sync.test",
            "google_calendar_oauth_client_id": "client",
            "oauth_state_secret": "s" * 32,
        }
    )
    gateway = build_gateway(settings, auth=AuthSettings(auth_mode="dev"), clock=FixedClock(now))
    app = FastAPI()
    mount(app, gateway)
    admin = create_async_engine(clean_db.admin)
    try:
        async with admin.begin() as conn:
            for uid in (user, other):
                await conn.execute(
                    text("INSERT INTO users (id, name) VALUES (:u, 'Member')"), {"u": uid}
                )
        respx.post("http://sync.test/integrations/garmin/test").respond(json={"ok": True})
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            headers = {"X-User-Id": str(user)}
            connected = await client.post(
                "/integrations/garmin/connect",
                headers=headers,
                json={"email": "member@example.com", "password": "private-password"},
            )
            assert connected.status_code == 200
            removed = await client.post(
                "/integrations/garmin/disconnect", headers={"X-User-Id": str(other)}
            )
            assert removed.status_code == 200
            async with admin.begin() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT payload_enc, payload_dev FROM integrations_credentials WHERE user_id=:u"
                        ),
                        {"u": user},
                    )
                ).one()
                assert row.payload_dev is None
                assert b"private-password" not in row.payload_enc
                assert open_json(
                    AesGcmSecretBox.from_settings(settings.secrets), row.payload_enc
                ) == {"email": "member@example.com", "password": "private-password"}
            start = await client.post("/integrations/google_calendar/start", headers=headers)
            assert start.status_code == 200
            state = start.json()["state"]
            wrong = await client.post(
                "/integrations/google_calendar/callback",
                headers={"X-User-Id": str(other)},
                json={"code": "c", "state": state},
            )
            assert wrong.status_code == 400
            assert wrong.json()["code"] == "bad_state"
            async with admin.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE oauth_state SET created_at=CAST(:now AS timestamptz) - interval '61 minutes' WHERE user_id=:u"
                    ),
                    {"now": now, "u": user},
                )
            expired = await client.post(
                "/integrations/google_calendar/callback",
                headers=headers,
                json={"code": "c", "state": state},
            )
            assert expired.status_code == 400
            assert expired.json()["code"] == "state_used"
            await client.patch("/me/profile", headers=headers, json={"height_cm": 180, "age": 35})
            own = await client.get("/me/profile", headers=headers)
            theirs = await client.get("/me/profile", headers={"X-User-Id": str(other)})
            assert own.json()["height_cm"] == 180
            assert theirs.json()["height_cm"] is None
    finally:
        await gateway.aclose()
        await admin.dispose()
