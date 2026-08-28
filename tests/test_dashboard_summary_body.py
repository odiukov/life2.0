import pytest
from orchestrator.app.main import _format_age


def test_format_age_today():
    assert _format_age(0) == "today"


def test_format_age_yesterday():
    assert _format_age(1) == "yesterday"


def test_format_age_three_days_ago():
    assert _format_age(3) == "3 days ago"


def test_format_age_one_day_alias():
    # 1 day uses "yesterday", not "1 days ago"
    assert _format_age(1) == "yesterday"


from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID

USER = UUID("00000000-0000-0000-0000-000000000001")


def _row(recorded_at, **data):
    return {
        "type": "body_composition",
        "recorded_at": recorded_at,
        "data": data,
        "source": "ViHealth",
    }


@pytest.mark.asyncio
async def test_featured_body_none_when_no_rows():
    from orchestrator.app.main import _build_featured_body
    with patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock) as mb:
        mb.return_value = []
        assert await _build_featured_body(USER) is None


@pytest.mark.asyncio
async def test_featured_body_none_when_one_row():
    from orchestrator.app.main import _build_featured_body
    now = datetime.now(timezone.utc)
    with patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock) as mb:
        mb.return_value = [_row(now, weight_kg=78.4)]
        assert await _build_featured_body(USER) is None


@pytest.mark.asyncio
async def test_featured_body_none_when_latest_older_than_60d():
    from orchestrator.app.main import _build_featured_body
    now = datetime.now(timezone.utc)
    with patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock) as mb:
        mb.return_value = [
            _row(now - timedelta(days=61), weight_kg=78.4),
            _row(now - timedelta(days=91), weight_kg=79.6),
        ]
        assert await _build_featured_body(USER) is None


@pytest.mark.asyncio
async def test_featured_body_none_when_latest_missing_weight():
    from orchestrator.app.main import _build_featured_body
    now = datetime.now(timezone.utc)
    with patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock) as mb:
        mb.return_value = [
            _row(now, body_fat_pct=22.1),  # no weight_kg
            _row(now - timedelta(days=30), weight_kg=79.6, body_fat_pct=22.9),
        ]
        assert await _build_featured_body(USER) is None


@pytest.mark.asyncio
async def test_featured_body_full_metrics_30d_anchor():
    from orchestrator.app.main import _build_featured_body
    now = datetime.now(timezone.utc)
    with patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock) as mb:
        mb.return_value = [
            _row(now - timedelta(days=3),
                 weight_kg=78.4, body_fat_pct=22.1,
                 muscle_kg=38.5, lean_mass_kg=61.1),
            _row(now - timedelta(days=33),  # 30 days before latest
                 weight_kg=79.6, body_fat_pct=22.9,
                 muscle_kg=38.4, lean_mass_kg=61.5),
        ]
        result = await _build_featured_body(USER)

    assert result is not None
    assert result["weightKg"] == 78.4
    assert result["weightDelta30d"] == -1.2
    assert result["fatPct"] == 22.1
    assert result["fatPctDelta30d"] == -0.8
    assert result["muscleKg"] == 38.5
    assert result["muscleKgDelta30d"] == 0.1
    assert result["leanKg"] == 61.1
    assert result["leanKgDelta30d"] == -0.4
    assert result["ageDaysLabel"] == "3 days ago"
    assert result["source"] == "ViHealth"
    # sparkline: oldest → newest, both rows have weight_kg
    assert result["sparkWeights"] == [79.6, 78.4]


@pytest.mark.asyncio
async def test_featured_body_only_weight_metric_present():
    from orchestrator.app.main import _build_featured_body
    now = datetime.now(timezone.utc)
    with patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock) as mb:
        mb.return_value = [
            _row(now - timedelta(days=2), weight_kg=78.4),
            _row(now - timedelta(days=32), weight_kg=79.6),
        ]
        result = await _build_featured_body(USER)

    assert result is not None
    assert result["weightKg"] == 78.4
    assert result["weightDelta30d"] == -1.2
    assert result["fatPct"] is None
    assert result["fatPctDelta30d"] is None
    assert result["muscleKg"] is None
    assert result["muscleKgDelta30d"] is None
    assert result["leanKg"] is None
    assert result["leanKgDelta30d"] is None


@pytest.mark.asyncio
async def test_featured_body_anchor_outside_window():
    from orchestrator.app.main import _build_featured_body
    now = datetime.now(timezone.utc)
    with patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock) as mb:
        mb.return_value = [
            _row(now - timedelta(days=3), weight_kg=78.4),
            _row(now - timedelta(days=53), weight_kg=82.0),  # 50d before latest
        ]
        result = await _build_featured_body(USER)

    assert result is not None
    assert result["weightKg"] == 78.4
    assert result["weightDelta30d"] is None  # anchor outside ±10d of -30d target
    # sparkline still uses both rows
    assert result["sparkWeights"] == [82.0, 78.4]


@pytest.mark.asyncio
async def test_featured_body_sparkline_orders_oldest_to_newest_and_caps_at_8():
    from orchestrator.app.main import _build_featured_body
    now = datetime.now(timezone.utc)
    # 10 weigh-ins, weight = age-in-days (so order is unambiguous)
    rows = [
        _row(now - timedelta(days=i), weight_kg=float(i))
        for i in range(10)
    ]
    with patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock) as mb:
        mb.return_value = rows
        result = await _build_featured_body(USER)

    assert result is not None
    # Newest 8 selected (i=0..7), reversed → oldest first → [7,6,5,4,3,2,1,0]
    assert result["sparkWeights"] == [7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0, 0.0]
    assert len(result["sparkWeights"]) == 8


def _make_pool_mock():
    """Return an AsyncMock that looks like an asyncpg pool with fetch/fetchrow returning empty results."""
    pool = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    return pool


@pytest.mark.asyncio
async def test_dashboard_summary_includes_featured_body():
    from orchestrator.app.main import dashboard_summary
    now = datetime.now(timezone.utc)
    rows = [
        _row(now - timedelta(days=2),
             weight_kg=78.4, body_fat_pct=22.1,
             muscle_kg=38.5, lean_mass_kg=61.1),
        _row(now - timedelta(days=32),
             weight_kg=79.6, body_fat_pct=22.9,
             muscle_kg=38.4, lean_mass_kg=61.5),
    ]
    pool_mock = _make_pool_mock()
    with patch("orchestrator.app.main.get_yesterday_metrics",
               new_callable=AsyncMock, return_value={}), \
         patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock, return_value=rows), \
         patch("orchestrator.app.db.get_body_profile",
               new_callable=AsyncMock, return_value={}), \
         patch("orchestrator.app.db.fetch_body_logs",
               new_callable=AsyncMock, return_value=rows), \
         patch("shared.db.get_pool",
               new_callable=AsyncMock, return_value=pool_mock):
        result = await dashboard_summary(user_id=USER)

    assert result["featured_body"] is not None
    assert result["featured_body"]["weightKg"] == 78.4
    assert result["featured_body"]["weightDelta30d"] == -1.2

    # Body tile must mirror featured_body so the home grid shows real data
    # (regression: previously the agents list omitted body and the tile
    # rendered as "—").
    body_tile = next((a for a in result["agents"] if a["agent"] == "body"), None)
    assert body_tile is not None
    assert body_tile["metric"] == "78.4 kg"
    assert "-1.2kg 30d" in (body_tile["detail"] or "")
    assert "Fat 22.1%" in (body_tile["detail"] or "")


@pytest.mark.asyncio
async def test_dashboard_summary_omits_body_tile_when_no_rows():
    from orchestrator.app.main import dashboard_summary
    pool_mock = _make_pool_mock()
    with patch("orchestrator.app.main.get_yesterday_metrics",
               new_callable=AsyncMock, return_value={}), \
         patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock, return_value=[]), \
         patch("orchestrator.app.db.get_body_profile",
               new_callable=AsyncMock, return_value={}), \
         patch("orchestrator.app.db.fetch_body_logs",
               new_callable=AsyncMock, return_value=[]), \
         patch("shared.db.get_pool",
               new_callable=AsyncMock, return_value=pool_mock):
        result = await dashboard_summary(user_id=USER)

    assert all(a["agent"] != "body" for a in result["agents"])


@pytest.mark.asyncio
async def test_featured_body_weight_delta_prev_uses_prior_weighin():
    from orchestrator.app.main import _build_featured_body
    now = datetime.now(timezone.utc)
    with patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock) as mb:
        mb.return_value = [
            _row(now - timedelta(days=2), weight_kg=77.1),
            _row(now - timedelta(days=10), weight_kg=77.7),
            _row(now - timedelta(days=16), weight_kg=79.6),
        ]
        result = await _build_featured_body(USER)

    assert result is not None
    # 77.1 - 77.7 = -0.6 (rounded)
    assert result["weightDeltaPrev"] == -0.6
    # No anchor exists within ±10d of latest-30d (target ~ -32d), so 30d is null.
    assert result["weightDelta30d"] is None


@pytest.mark.asyncio
async def test_featured_body_weight_delta_prev_skips_fat_only_rows():
    from orchestrator.app.main import _build_featured_body
    now = datetime.now(timezone.utc)
    with patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock) as mb:
        mb.return_value = [
            _row(now - timedelta(days=2), weight_kg=77.1),
            _row(now - timedelta(days=5), body_fat_pct=23.0),  # no weight_kg
            _row(now - timedelta(days=8), weight_kg=78.0),
        ]
        result = await _build_featured_body(USER)

    assert result is not None
    # Skips the fat-only row at -5d, falls through to -8d row.
    assert result["weightDeltaPrev"] == -0.9


@pytest.mark.asyncio
async def test_dashboard_summary_featured_body_null_when_no_rows():
    from orchestrator.app.main import dashboard_summary
    pool_mock = _make_pool_mock()
    with patch("orchestrator.app.main.get_yesterday_metrics",
               new_callable=AsyncMock, return_value={}), \
         patch("orchestrator.app.main.fetch_body_logs",
               new_callable=AsyncMock, return_value=[]), \
         patch("orchestrator.app.db.get_body_profile",
               new_callable=AsyncMock, return_value={}), \
         patch("orchestrator.app.db.fetch_body_logs",
               new_callable=AsyncMock, return_value=[]), \
         patch("shared.db.get_pool",
               new_callable=AsyncMock, return_value=pool_mock):
        result = await dashboard_summary(user_id=USER)

    assert result["featured_body"] is None
