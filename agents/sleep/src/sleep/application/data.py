"""Recent sleep sessions (every source) and overnight HRV, for the model."""

from __future__ import annotations

from datetime import datetime

from shared.a2a.request import SkillRequest
from shared.analysis.prompt import PromptSection
from shared.analysis.skill import AnalysisData, LoadedData
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork
from shared.ports.users import UserSettings

from sleep.domain.session import SleepSession, session_line

SESSIONS = 10
HRV_DAYS = 7


class SleepData(AnalysisData):
    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData:
        repo = uow.repo(HealthLogRepository)
        sessions = await repo.recent(request.user_id, types=["sleep_session"], limit=SESSIONS)
        hrv = await repo.recent(request.user_id, types=["hrv_status"], limit=HRV_DAYS)
        session_text = "\n".join(
            session_line(SleepSession.from_row(r), settings.timezone) for r in sessions
        )
        hrv_lines = [
            f"- {r.recorded_at.astimezone(settings.timezone).date()} | rmssd={r.data.get('hrv_rmssd')}"
            + (f" | {r.data['status']}" if r.data.get("status") else "")
            for r in hrv
        ]
        return LoadedData(
            [
                PromptSection(
                    f"Recent sleep sessions (last {SESSIONS})",
                    session_text or "No recent sleep logs.",
                ),
                PromptSection(
                    f"Overnight HRV (last {HRV_DAYS})", "\n".join(hrv_lines) or "No HRV data."
                ),
            ]
        )
