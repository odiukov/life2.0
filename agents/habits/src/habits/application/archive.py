from __future__ import annotations

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.ports.vector_memory import VectorMemory

from habits.application.check import find_habit
from habits.application.ports import HabitRepository


class ArchiveHabit:
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
            active = await tx.repo(HabitRepository).active()
        habit = await find_habit(request, active, self._llm)
        if habit is None or habit.id is None:
            return SkillResult(output=self._tr.t("habits.archive.not_found", locale))
        async with self._uow.for_user(uid) as tx:
            archived = await tx.repo(HabitRepository).archive(habit.id)
        if not archived:
            return SkillResult(output=self._tr.t("habits.archive.already", locale, name=habit.name))
        output = self._tr.t("habits.archive.done", locale, name=habit.name)
        return SkillResult(output=output, log_entry=output)
