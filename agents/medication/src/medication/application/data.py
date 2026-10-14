"""analyze_adherence: per medication, its schedule and the intakes in the window."""

from __future__ import annotations

from datetime import datetime, timedelta

from shared.a2a.request import SkillRequest
from shared.analysis.prompt import PromptSection
from shared.analysis.skill import AnalysisData, LoadedData
from shared.ports.health_logs import HealthLogRepository
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork
from shared.ports.users import UserSettings

from medication.application.ports import MedicationRepository
from medication.domain.medication import Intake

DEFAULT_WINDOW = 14
MAX_WINDOW = 90


def window_days(raw: object) -> int:
    try:
        value = int(str(raw))
    except (TypeError, ValueError):
        return DEFAULT_WINDOW
    return min(max(value, 1), MAX_WINDOW)


class AdherenceData(AnalysisData):
    def __init__(self, translator: Translator, default_locale: str) -> None:
        self._tr = translator
        self._default_locale = default_locale

    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData:
        active = await uow.repo(MedicationRepository).active()
        if not active:
            locale = settings.locale or self._default_locale
            return LoadedData([], answer=self._tr.t("medication.analyze.none", locale))
        days = window_days(request.params.get("window_days"))
        rows = await uow.repo(HealthLogRepository).recent(
            request.user_id,
            types=["medication_taken"],
            agent="medication",
            since=now - timedelta(days=days),
        )
        intakes = [Intake.from_row(r) for r in rows]
        lines = []
        for m in active:
            mine = [
                i
                for i in intakes
                if i.medication_id == str(m.id) or (i.medication_id is None and i.name == m.name)
            ]
            last = max((i.at for i in mine), default=None)
            lines.append(
                f"- {m.name} | schedule: {m.schedule} | dose: {m.dose or '—'} | taken {len(mine)}× | last: "
                + (f"{last.astimezone(settings.timezone):%Y-%m-%d %H:%M}" if last else "never")
            )
        return LoadedData(
            [
                PromptSection("Adherence window", f"Last {days} days"),
                PromptSection("Per-medication summary", "\n".join(lines)),
            ]
        )
