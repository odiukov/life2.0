import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
import sync_service.app.sync  # pre-import so patch() can resolve the module


MOCK_GARMIN_DATA = {
    "sleep": [
        ("2026-04-13", {
            "dailySleepDTO": {
                "sleepTimeSeconds": 27180,
                "deepSleepSeconds": 5400,
                "lightSleepSeconds": 12600,
                "remSleepSeconds": 6300,
                "awakeSleepSeconds": 2880,
                "sleepStartTimestampLocal": 1744506900000,
                "sleepEndTimestampLocal": 1744531680000,
                "sleepScores": {"overall": {"value": 82}},
                "averageHRV": 54,
            }
        }),
    ],
    "activities": [
        {
            "activityId": 12345678,
            "activityName": "Morning Run",
            "activityType": {"typeKey": "running"},
            "duration": 2580.0,
            "distance": 5240.0,
            "calories": 412,
            "averageHR": 158,
            "maxHR": 181,
            "startTimeLocal": "2026-04-13 07:00:00",
        }
    ],
    "daily_stats": [
        ("2026-04-13", {
            "totalSteps": 9823,
            "activeKilocalories": 620,
            "averageStressLevel": 28,
            "minBodyBattery": 14,
            "maxBodyBattery": 87,
            "restingHeartRate": 52,
        }),
    ],
    "errors": [],
}


@pytest.mark.asyncio
async def test_sync_endpoint_inserts_and_returns_counts():
    """POST /sync maps Garmin data and writes to DB, returns synced/skipped counts."""
    with patch("sync_service.app.sync.list_user_credentials", new=AsyncMock(return_value=[("user-1", {"email": "a@b.com", "password": "p"})])):
        with patch("sync_service.app.sync.fetch_all", new=AsyncMock(return_value=(MOCK_GARMIN_DATA, "mock_token"))):
            with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(3, 0))):
                with patch("sync_service.app.sync.session.get_garmin_token", new=AsyncMock(return_value=None)):
                    with patch("sync_service.app.sync.session.save_garmin_token", new=AsyncMock()):
                        from sync_service.app.main import app
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                            resp = await client.post("/sync")

    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] == 3
    assert body["skipped"] == 0
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_sync_endpoint_dedup_skips():
    """POST /sync with duplicate data reports skipped count."""
    with patch("sync_service.app.sync.list_user_credentials", new=AsyncMock(return_value=[("user-1", {"email": "a@b.com", "password": "p"})])):
        with patch("sync_service.app.sync.fetch_all", new=AsyncMock(return_value=(MOCK_GARMIN_DATA, "mock_token"))):
            with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(0, 3))):
                with patch("sync_service.app.sync.session.get_garmin_token", new=AsyncMock(return_value=None)):
                    with patch("sync_service.app.sync.session.save_garmin_token", new=AsyncMock()):
                        from sync_service.app.main import app
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                            resp = await client.post("/sync")

    assert resp.status_code == 200
    body = resp.json()
    assert body["synced"] == 0
    assert body["skipped"] == 3


@pytest.mark.asyncio
async def test_sync_endpoint_garmin_errors_reported():
    """POST /sync propagates Garmin fetch errors in response."""
    data_with_error = {**MOCK_GARMIN_DATA, "errors": ["sleep 2026-04-12: timeout"]}
    with patch("sync_service.app.sync.list_user_credentials", new=AsyncMock(return_value=[("user-1", {"email": "a@b.com", "password": "p"})])):
        with patch("sync_service.app.sync.fetch_all", new=AsyncMock(return_value=(data_with_error, "mock_token"))):
            with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(2, 0))):
                with patch("sync_service.app.sync.session.get_garmin_token", new=AsyncMock(return_value=None)):
                    with patch("sync_service.app.sync.session.save_garmin_token", new=AsyncMock()):
                        from sync_service.app.main import app
                        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                            resp = await client.post("/sync")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["errors"]) == 1
    assert "sleep 2026-04-12" in body["errors"][0]


@pytest.mark.asyncio
async def test_do_sync_does_not_save_empty_token():
    """When fetch_all returns empty token_out (dumps() failed), session.save is not called."""
    with patch("sync_service.app.sync.list_user_credentials", new=AsyncMock(return_value=[("user-1", {"email": "a@b.com", "password": "p"})])):
        with patch("sync_service.app.sync.fetch_all", new=AsyncMock(return_value=(MOCK_GARMIN_DATA, ""))):
            with patch("sync_service.app.sync.insert_rows", new=AsyncMock(return_value=(0, 0))):
                with patch("sync_service.app.sync.session.get_garmin_token", new=AsyncMock(return_value="old_valid_token")):
                    save_mock = AsyncMock()
                    with patch("sync_service.app.sync.session.save_garmin_token", new=save_mock):
                        from sync_service.app.sync import do_sync
                        await do_sync()
    save_mock.assert_not_called()


@pytest.mark.asyncio
async def test_health_endpoint():
    from sync_service.app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
