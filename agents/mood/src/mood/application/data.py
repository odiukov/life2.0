from __future__ import annotations

from datetime import datetime

from shared.a2a.request import SkillRequest
from shared.analysis.prompt import PromptSection
from shared.analysis.skill import AnalysisData, LoadedData
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork
from shared.ports.users import UserSettings
from shared.skill_ids import Mood

from mood.domain.entry import MoodEntry, mood_line

HISTORY = 30
EMPTY_TAILS = {
    Mood.ANALYZE: "There are not enough mood entries to analyze. Tell the user to log a few days first.",
    Mood.RECOMMENDATIONS: (
        "There is no mood history. Ask the user to log a few entries so you can recommend based on actual data."
    ),
}


class MoodData(AnalysisData):
    def __init__(self, mode: str) -> None:
        self._mode = mode

    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData:
        rows = await uow.repo(HealthLogRepository).recent(
            request.user_id, types=["mood"], limit=HISTORY
        )
        lines = [mood_line(MoodEntry.from_row(r), settings.timezone) for r in rows]
        section = PromptSection(
            f"Recent mood entries (latest {HISTORY})", "\n".join(lines) or "No mood entries yet."
        )
        return LoadedData([section], tail_override=None if rows else EMPTY_TAILS.get(self._mode))
