from uuid import uuid4

import pytest
from sync.application.check_credentials import CheckCredentials
from sync.application.ingest_body import IngestBody, IngestResult
from sync.application.ports import AuthFailed, Credentials, Unavailable
from sync.testing import FakeGarminClient, FakeYazioClient, MemoryBackend
from sync_fixtures import BODY_ENTRIES

USER = uuid4()
CREDS = Credentials("a@b.c", "pw")


async def test_body_entries_are_grouped_and_upserted_under_the_users_tenant() -> None:
    backend = MemoryBackend()
    ingest = IngestBody(uow=backend.uow)
    assert await ingest(USER, BODY_ENTRIES) == IngestResult(written=2, unchanged=0)
    assert await ingest(USER, BODY_ENTRIES) == IngestResult(written=0, unchanged=2)
    assert {r.type for r in backend.logs.rows[USER]} == {"body_composition"}
    assert backend.uow.commits == [USER, USER]


async def test_body_without_known_metrics_writes_nothing() -> None:
    backend = MemoryBackend()
    assert await IngestBody(uow=backend.uow)(
        USER, [{"name": "Heart Rate", "qty": 60, "date": "2026-04-14"}]
    ) == IngestResult(0, 0)
    assert backend.uow.commits == []


@pytest.mark.parametrize(
    ("garmin", "service", "expected"),
    [
        (FakeGarminClient(), "garmin", "ok"),
        (FakeGarminClient(check_error=AuthFailed()), "garmin", "auth_failed"),
        (FakeGarminClient(check_error=Unavailable()), "garmin", "unavailable"),
    ],
)
async def test_check_maps_outcomes(garmin: FakeGarminClient, service: str, expected: str) -> None:
    assert await CheckCredentials(garmin=garmin, yazio=None)(service, CREDS) == expected  # type: ignore[arg-type]
    assert garmin.checks == [CREDS]


async def test_check_without_yazio_settings_is_disabled() -> None:
    assert (
        await CheckCredentials(garmin=FakeGarminClient(), yazio=None)("yazio", CREDS) == "disabled"
    )
    yazio = FakeYazioClient()
    assert await CheckCredentials(garmin=FakeGarminClient(), yazio=yazio)("yazio", CREDS) == "ok"
