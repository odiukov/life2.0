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

from habits.application.ports import HabitRepository
from habits.domain.habit import Habit, check_data


def _float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


async def find_habit(request: SkillRequest, active: list[Habit], llm: LLMProvider) -> Habit | None:
    """habit_id param → name param → the message, matched across languages."""
    raw_id = request.params.get("habit_id")
    if isinstance(raw_id, str):
        match = next((h for h in active if str(h.id) == raw_id), None)
        if match is not None:
            return match
    raw_name = request.params.get("name")
    query = raw_name if isinstance(raw_name, str) and raw_name.strip() else request.text
    name = await resolve_name(query, [h.name for h in active], llm=llm)
    return next((h for h in active if h.name == name), None)


class CheckHabit:
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
            active = await tx.repo(HabitRepository).active()
        habit = await find_habit(request, active, self._llm)
        if habit is None:
            return SkillResult(output=self._tr.t("habits.check.not_found", locale))
        value = _float(request.params.get("value"))
        unit_param = request.params.get("unit")
        unit = unit_param if isinstance(unit_param, str) and unit_param else habit.unit
        note_param = request.params.get("note")
        note = note_param if isinstance(note_param, str) else None
        source_param = request.params.get("source")
        source = source_param if isinstance(source_param, str) and source_param else "manual"
        now = self._clock.now()
        async with self._uow.for_user(uid) as tx:
            stored_at = await tx.repo(HealthLogRepository).add(
                uid,
                HealthLogRow(
                    type="habit",
                    recorded_at=now,
                    data=check_data(habit, request.text, value, unit, note),
                    source=source,
                    agent="habits",
                ),
            )
        value_text = (
            self._tr.t("habits.check.value", locale, value=f"{value:g}", unit=unit or "")
            if value is not None
            else ""
        )
        output = self._tr.t("habits.check.done", locale, name=habit.name, value=value_text)
        with suppress(Exception):
            await self._memory.upsert(
                user_id=uid,
                agent="habits",
                key=request.task_id,
                text=request.text,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(output=output, log_entry=request.text, log_recorded_at=stored_at)
