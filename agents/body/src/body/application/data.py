"""What the body agent puts in front of the model."""

from __future__ import annotations

from datetime import datetime

from shared.a2a.request import SkillRequest
from shared.analysis.prompt import PromptSection
from shared.analysis.skill import AnalysisData, LoadedData
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork
from shared.ports.users import UserSettings

from body.domain.measurement import BodyMeasurement, measurement_line

BODY_TYPE = "body_composition"
HISTORY = 30
EMPTY = "No body composition measurements yet — ask the user to upload a ViHealth PDF."


class BodyData(AnalysisData):
    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData:
        rows = await uow.repo(HealthLogRepository).recent(
            request.user_id, types=[BODY_TYPE], limit=HISTORY
        )
        lines = [measurement_line(BodyMeasurement.from_row(r), settings.timezone) for r in rows]
        return LoadedData(
            [
                PromptSection(
                    f"Body composition history (latest {HISTORY})", "\n".join(lines) or EMPTY
                )
            ]
        )
