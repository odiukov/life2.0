from __future__ import annotations

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository

from medication.application.ports import MedicationRepository


class ListActive:
    def __init__(
        self, *, uow: UnitOfWorkFactory, translator: Translator, default_locale: str
    ) -> None:
        self._uow = uow
        self._tr = translator
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        async with self._uow.for_user(request.user_id) as tx:
            locale = (
                await tx.repo(UserSettingsRepository).get(request.user_id)
            ).locale or self._default_locale
            active = await tx.repo(MedicationRepository).active()
        if not active:
            return SkillResult(output=self._tr.t("medication.list.none", locale))
        lines = [
            self._tr.t(
                "medication.list.line",
                locale,
                name=m.name,
                dose=self._tr.t("medication.dose", locale, dose=m.dose) if m.dose else "",
                schedule=m.schedule,
            )
            for m in active
        ]
        return SkillResult(output="\n".join(lines))
