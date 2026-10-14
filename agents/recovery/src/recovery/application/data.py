"""Snapshot (bucket + latest vs 7-day baseline) and the last 7 days, for the model."""

from __future__ import annotations

from datetime import datetime, timedelta

from shared.a2a.request import SkillRequest
from shared.analysis.prompt import PromptSection
from shared.analysis.skill import AnalysisData, LoadedData
from shared.domain.recovery import baseline_mean, compute_bucket
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork
from shared.ports.users import UserSettings
from shared.skill_ids import Recovery

from recovery.domain.daily import RECOVERY_TYPES, DailyRecovery, assemble_days

NO_DATA_TAIL = (
    "There is no recovery data available yet (the device sync may be empty or offline). "
    "Tell the user: readiness unknown — come back after the next sync."
)


def window_days(mode: str) -> int:
    return 14 if mode == Recovery.ANALYZE_TREND else 8


def _day_line(d: DailyRecovery) -> str:
    bits = []
    if d.hrv is not None:
        bits.append(f"HRV={d.hrv}")
    if d.rhr is not None:
        bits.append(f"RHR={d.rhr}")
    if d.stress is not None:
        bits.append(f"stress={d.stress}")
    if d.bb_max is not None:
        bits.append(f"body_battery={d.bb_min if d.bb_min is not None else '?'}/{d.bb_max}")
    if d.sleep_score is not None:
        bits.append(f"sleep_score={d.sleep_score}")
    if d.sleep_duration_h is not None:
        bits.append(f"sleep_h={d.sleep_duration_h}")
    return f"{d.day}: " + ", ".join(bits)


class RecoveryData(AnalysisData):
    def __init__(self, mode: str) -> None:
        self._mode = mode

    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData:
        since = now - timedelta(days=window_days(self._mode))
        rows = await uow.repo(HealthLogRepository).recent(
            request.user_id, types=list(RECOVERY_TYPES), since=since
        )
        days = assemble_days(rows, settings.timezone)
        if not days:
            return LoadedData(
                [PromptSection("Snapshot", "No recovery data available yet.")],
                tail_override=NO_DATA_TAIL,
            )
        ordered = [days[k] for k in sorted(days, reverse=True)]
        current, baseline_days = ordered[0], ordered[1:8]
        baseline = baseline_mean([d.metrics() for d in baseline_days])
        bucket = compute_bucket(current.metrics(), baseline)

        def avg(values: list[float | int | None]) -> float | None:
            present = [float(v) for v in values if v is not None]
            return round(sum(present) / len(present), 1) if present else None

        snapshot = (
            f"Bucket: {bucket}\n"
            f"Latest ({current.day}): HRV={current.hrv}, RHR={current.rhr}, stress={current.stress}, "
            f"body_battery={current.bb_min}/{current.bb_max}, sleep_h={current.sleep_duration_h}\n"
            f"7-day baseline: HRV={avg([d.hrv for d in baseline_days])}, RHR={avg([d.rhr for d in baseline_days])}, "
            f"stress={avg([d.stress for d in baseline_days])}, body_battery_max={avg([d.bb_max for d in baseline_days])}"
        )
        history = "\n".join(_day_line(d) for d in ordered[:7])
        return LoadedData(
            [PromptSection("Snapshot", snapshot), PromptSection("Last 7 days", history)]
        )
