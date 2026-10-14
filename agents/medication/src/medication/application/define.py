from __future__ import annotations

from contextlib import suppress

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock
from shared.ports.llm import LLMError, LLMInvalidOutput, LLMProvider, LLMTask
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.ports.vector_memory import VectorMemory

from medication.application.ports import DuplicateMedication, MedicationRepository
from medication.application.schemas import MedicationDefinition
from medication.domain.medication import Medication

SYSTEM = """You turn a free-text medication or supplement description into a definition.
- name: a short lowercase kebab-case English name; translate other languages ("витамин D" → vitamin-d).
- dose: as stated, or null. schedule: free text as stated ("every morning", "mon,wed,fri 21:00"); required.
- notes: anything else useful (with food, before sleep), or null."""


class DefineMedication:
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
        self._tr = translator
        self._memory = memory
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        uid = request.user_id
        async with self._uow.for_user(uid) as tx:
            locale = (await tx.repo(UserSettingsRepository).get(uid)).locale or self._default_locale
        try:
            d = await self._llm.structured(
                task=LLMTask.FAST, system=SYSTEM, user=request.text, schema=MedicationDefinition
            )
        except LLMInvalidOutput:
            return SkillResult(output=self._tr.t("medication.define.not_understood", locale))
        except LLMError:
            return SkillResult(
                output=self._tr.t("analysis.errors.llm_unavailable", locale), failed=True
            )
        try:
            async with self._uow.for_user(uid) as tx:
                await tx.repo(MedicationRepository).add(
                    Medication(None, d.name, d.dose, d.schedule, d.notes, None)
                )
        except DuplicateMedication:
            return SkillResult(output=self._tr.t("medication.define.exists", locale, name=d.name))
        dose = self._tr.t("medication.dose", locale, dose=d.dose) if d.dose else ""
        output = self._tr.t(
            "medication.define.created", locale, name=d.name, dose=dose, schedule=d.schedule
        )
        with suppress(Exception):
            await self._memory.upsert(
                user_id=uid,
                agent="medication",
                key=request.task_id,
                text=output,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(output=output)
