from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.asyncio

from orchestrator.app.alerts import Alert
from orchestrator.app.alert_registry import AlertRegistry


def make_alert(rule_id: str, throttle_hours: int = 12) -> Alert:
    return Alert(
        rule_id=rule_id, severity="warn", message="m",
        category="wellness", throttle_hours=throttle_hours,
    )


async def test_fresh_alert_passes_when_never_emitted():
    fetch = AsyncMock(return_value=None)
    upsert = AsyncMock()
    reg = AlertRegistry(fetch_last=fetch, upsert_last=upsert)

    now = datetime(2026, 4, 19, 9, 0, tzinfo=timezone.utc)
    alerts = [make_alert("r1")]
    fresh = await reg.filter_fresh(alerts, now=now)
    assert [a.rule_id for a in fresh] == ["r1"]


async def test_throttled_alert_filtered_out():
    last = datetime(2026, 4, 19, 6, 0, tzinfo=timezone.utc)  # 3h ago at now=9:00
    fetch = AsyncMock(return_value=last)
    upsert = AsyncMock()
    reg = AlertRegistry(fetch_last=fetch, upsert_last=upsert)

    now = datetime(2026, 4, 19, 9, 0, tzinfo=timezone.utc)
    alerts = [make_alert("r1", throttle_hours=12)]
    fresh = await reg.filter_fresh(alerts, now=now)
    assert fresh == []


async def test_expired_throttle_passes():
    last = datetime(2026, 4, 18, 18, 0, tzinfo=timezone.utc)  # 15h ago
    fetch = AsyncMock(return_value=last)
    upsert = AsyncMock()
    reg = AlertRegistry(fetch_last=fetch, upsert_last=upsert)

    now = datetime(2026, 4, 19, 9, 0, tzinfo=timezone.utc)
    alerts = [make_alert("r1", throttle_hours=12)]
    fresh = await reg.filter_fresh(alerts, now=now)
    assert [a.rule_id for a in fresh] == ["r1"]


async def test_mark_emitted_writes_all():
    fetch = AsyncMock(return_value=None)
    upsert = AsyncMock()
    reg = AlertRegistry(fetch_last=fetch, upsert_last=upsert)

    now = datetime(2026, 4, 19, 9, 0, tzinfo=timezone.utc)
    alerts = [make_alert("r1"), make_alert("r2")]
    await reg.mark_emitted(alerts, now=now)
    assert upsert.await_count == 2
    upsert.assert_any_await("r1", now)
    upsert.assert_any_await("r2", now)
