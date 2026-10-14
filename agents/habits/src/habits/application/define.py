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

from habits.application.ports import DuplicateHabit, HabitRepository
from habits.application.schemas import HabitDefinition
from habits.domain.habit import Cadence, Habit, Kind

SYSTEM = """You turn a free-text habit description into a habit definition.
- A numeric target ("20 minutes", "30 pages", "5 km") means kind=quantitative with target_value and unit;
  otherwise kind=boolean.
- "every day" / "daily" / "ежедневно" / nothing specific → cadence_type=daily.
- Named days ("Mon/Wed/Fri", "по пн/ср/пт", "weekends") → cadence_type=weekly with cadence_days (mon..sun).
- name: a short lowercase kebab-case English name; translate other languages ("медитация" → meditation)."""


class DefineHabit:
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

    def _cadence(self, d: HabitDefinition, locale: str) -> str:
        if d.cadence_type == "daily":
            return self._tr.t("habits.cadence.daily", locale)
        return self._tr.t("habits.cadence.weekly", locale, days=", ".join(d.cadence_days or []))

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        uid = request.user_id
        async with self._uow.for_user(uid) as tx:
            locale = (await tx.repo(UserSettingsRepository).get(uid)).locale or self._default_locale
        try:
            d = await self._llm.structured(
                task=LLMTask.FAST, system=SYSTEM, user=request.text, schema=HabitDefinition
            )
        except LLMInvalidOutput:
            return SkillResult(output=self._tr.t("habits.define.not_understood", locale))
        except LLMError:
            return SkillResult(
                output=self._tr.t("analysis.errors.llm_unavailable", locale), failed=True
            )
        habit = Habit(
            id=None,
            name=d.name,
            kind=Kind(d.kind),
            cadence=Cadence(d.cadence_type),
            cadence_days=tuple(d.cadence_days or ()),
            target_value=d.target_value,
            unit=d.unit,
            created_at=None,
        )
        try:
            async with self._uow.for_user(uid) as tx:
                await tx.repo(HabitRepository).add(habit)
        except DuplicateHabit:
            return SkillResult(output=self._tr.t("habits.define.exists", locale, name=d.name))
        output = self._tr.t(
            "habits.define.created", locale, name=d.name, cadence=self._cadence(d, locale)
        )
        with suppress(Exception):
            await self._memory.upsert(
                user_id=uid,
                agent="habits",
                key=request.task_id,
                text=output,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(output=output)
