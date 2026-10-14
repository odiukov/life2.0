from __future__ import annotations

from contextlib import suppress

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.analysis.matching import resolve_name
from shared.ports.clock import Clock
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.llm import LLMProvider
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.ports.vector_memory import VectorMemory

from medication.application.ports import MedicationRepository
from medication.domain.medication import Medication, intake_data


async def find_medication(
    request: SkillRequest, active: list[Medication], llm: LLMProvider
) -> Medication | None:
    raw = request.params.get("name")
    query = raw if isinstance(raw, str) and raw.strip() else request.text
    name = await resolve_name(query, [m.name for m in active], llm=llm)
    return next((m for m in active if m.name == name), None)


class LogIntake:
    def __init__(
        self,
        *,
        llm: LLMProvider,
        uow: UnitOfWorkFactory,
        clock: Clock,
        translator: Translator,
        memory: VectorMemory,
        default_locale: str,
    ) -> None:
        self._llm = llm
        self._uow = uow
        self._clock = clock
        self._tr = translator
        self._memory = memory
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        uid = request.user_id
        async with self._uow.for_user(uid) as tx:
            locale = (await tx.repo(UserSettingsRepository).get(uid)).locale or self._default_locale
            active = await tx.repo(MedicationRepository).active()
        med = await find_medication(request, active, self._llm)
        if med is None:
            return SkillResult(output=self._tr.t("medication.log.not_found", locale))
        override = request.params.get("dose_override")
        dose = override if isinstance(override, str) and override else med.dose
        note_param = request.params.get("note")
        note = note_param if isinstance(note_param, str) else None
        source_param = request.params.get("source")
        source = source_param if isinstance(source_param, str) and source_param else "manual"
        now = self._clock.now()
        async with self._uow.for_user(uid) as tx:
            stored_at = await tx.repo(HealthLogRepository).add(
                uid,
                HealthLogRow(
                    type="medication_taken",
                    recorded_at=now,
                    data=intake_data(med, request.text, dose, note),
                    source=source,
                    agent="medication",
                ),
            )
        dose_text = self._tr.t("medication.dose", locale, dose=dose) if dose else ""
        output = self._tr.t("medication.log.done", locale, name=med.name, dose=dose_text)
        with suppress(Exception):
            await self._memory.upsert(
                user_id=uid,
                agent="medication",
                key=request.task_id,
                text=output,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(output=output, log_entry=output, log_recorded_at=stored_at)
