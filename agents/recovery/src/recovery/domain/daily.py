"""One recovery picture per day from Garmin, HealthKit and chat rows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

RECOVERY_TYPES = ("sleep_session", "daily_stats", "hrv_status")
# Rows whose recorded_at marks a calendar day rather than a moment.
DATE_KEYED_TYPES = frozenset({"daily_stats", "hrv_status"})
CHAT = "chat"


class _Row(Protocol):
    @property
    def type(self) -> str: ...

    @property
    def recorded_at(self) -> datetime: ...

    @property
    def data(self) -> Mapping[str, Any]: ...

    @property
    def source(self) -> str: ...


def _num(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _first(data: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _num(data.get(key))
        if value is not None:
            return value
    return None


def _clean(value: float | None) -> float | int | None:
    return int(value) if value is not None and value.is_integer() else value


def row_day(row: _Row, zone: ZoneInfo) -> date:
    if row.type in DATE_KEYED_TYPES or (row.type == "sleep_session" and row.source == "HealthKit"):
        return row.recorded_at.astimezone(UTC).date()
    return row.recorded_at.astimezone(zone).date()


@dataclass(frozen=True, slots=True)
class DailyRecovery:
    day: date
    hrv: float | int | None
    hrv_source: str | None
    rhr: float | int | None
    stress: float | int | None
    bb_min: float | int | None
    bb_max: float | int | None
    sleep_score: float | int | None
    sleep_duration_h: float | None
    sleep_efficiency_pct: float | None

    def metrics(self) -> dict[str, float | int | None]:
        """The compute_bucket / baseline_mean contract."""
        return {
            "hrv_sdnn": self.hrv,
            "rhr": self.rhr,
            "sleep_efficiency_pct": self.sleep_efficiency_pct,
            "sleep_duration_h": self.sleep_duration_h,
        }


def _session(rows: list[_Row]) -> _Row | None:
    devices = [r for r in rows if r.source != CHAT]
    pool = devices or rows
    return max(pool, key=lambda r: _num(r.data.get("duration_seconds")) or 0.0) if pool else None


def assemble_days(rows: Iterable[_Row], zone: ZoneInfo) -> dict[date, DailyRecovery]:
    by_day: dict[date, dict[str, list[_Row]]] = {}
    for row in rows:
        by_day.setdefault(row_day(row, zone), {}).setdefault(row.type, []).append(row)
    out: dict[date, DailyRecovery] = {}
    for day, groups in by_day.items():
        stats = [r.data for r in groups.get("daily_stats", [])]
        hrv_status = [_num(r.data.get("hrv_rmssd")) for r in groups.get("hrv_status", [])]
        session = _session(groups.get("sleep_session", []))
        sdata = session.data if session is not None else {}

        def stat(*keys: str, values: list[Mapping[str, Any]] = stats) -> float | None:
            return next((v for d in values if (v := _first(d, *keys)) is not None), None)

        hrv, hrv_source = next((v for v in hrv_status if v is not None), None), "hrv_status"
        if hrv is None:
            hrv, hrv_source = stat("heartRateVariabilitySDNN"), "daily_stats"
        if hrv is None:
            hrv, hrv_source = _num(sdata.get("hrv_weekly_avg")), "sleep_session"
        duration = _num(sdata.get("duration_seconds"))
        awake = _num(sdata.get("awake_seconds"))
        out[day] = DailyRecovery(
            day=day,
            hrv=_clean(hrv),
            hrv_source=hrv_source if hrv is not None else None,
            rhr=_clean(stat("resting_hr", "restingHeartRate")),
            stress=_clean(stat("stress_avg")),
            bb_min=_clean(stat("body_battery_min")),
            bb_max=_clean(stat("body_battery_max")),
            sleep_score=_clean(_num(sdata.get("score"))),
            sleep_duration_h=round(duration / 3600, 2) if duration else None,
            sleep_efficiency_pct=round(max(0.0, (duration - awake) / duration * 100), 1)
            if duration and awake is not None
            else None,
        )
    return out
