from __future__ import annotations

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.ports.vector_memory import VectorMemory

from medication.application.intake import find_medication
from medication.application.ports import MedicationRepository


class ArchiveMedication:
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
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        uid = request.user_id
        async with self._uow.for_user(uid) as tx:
            locale = (await tx.repo(UserSettingsRepository).get(uid)).locale or self._default_locale
            active = await tx.repo(MedicationRepository).active()
        med = await find_medication(request, active, self._llm)
        if med is None or med.id is None:
            return SkillResult(output=self._tr.t("medication.archive.not_found", locale))
        async with self._uow.for_user(uid) as tx:
            archived = await tx.repo(MedicationRepository).archive(med.id)
        if not archived:
            return SkillResult(
                output=self._tr.t("medication.archive.already", locale, name=med.name)
            )
        output = self._tr.t("medication.archive.done", locale, name=med.name)
        return SkillResult(output=output, log_entry=output)
