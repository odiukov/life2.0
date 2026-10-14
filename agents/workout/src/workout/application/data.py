"""Recent workouts (activity rows only) and the last body measurements, for the model."""

from __future__ import annotations

from datetime import datetime

from body.domain.measurement import BodyMeasurement
from shared.a2a.request import SkillRequest
from shared.analysis.prompt import PromptSection
from shared.analysis.skill import AnalysisData, LoadedData
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork
from shared.ports.users import UserSettings

from workout.domain.workout import Workout, workout_line

WORKOUTS = 10
BODY = 5


def _body_line(m: BodyMeasurement, settings: UserSettings) -> str:
    return (
        f"- {m.recorded_at.astimezone(settings.timezone).date()} | weight={m.weight_kg}kg | fat={m.body_fat_pct}% "
        f"| muscle={m.skeletal_muscle_kg}kg | lean={m.lean_mass_kg}kg"
    )


class WorkoutData(AnalysisData):
    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData:
        repo = uow.repo(HealthLogRepository)
        workouts = await repo.recent(request.user_id, types=["activity"], limit=WORKOUTS)
        body = await repo.recent(request.user_id, types=["body_composition"], limit=BODY)
        return LoadedData(
            [
                PromptSection(
                    f"Recent workouts (last {WORKOUTS})",
                    "\n".join(
                        workout_line(Workout.from_row(r), settings.timezone) for r in workouts
                    )
                    or "No recent workout logs.",
                ),
                PromptSection(
                    f"Body composition (last {BODY} measurements)",
                    "\n".join(_body_line(BodyMeasurement.from_row(r), settings) for r in body)
                    or "No body composition data.",
                ),
            ]
        )
