from __future__ import annotations

from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock
from shared.ports.llm import LLMError, LLMInvalidOutput, LLMProvider, LLMTask
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.vector_memory import VectorMemory

from nutrition.application.ports import MealRepository, ProfileRepository
from nutrition.application.rendering import meal_confirmation
from nutrition.application.schemas import MealExtraction
from nutrition.domain.day import resolve_eaten_at
from nutrition.domain.meal import CHAT_SOURCE, Macros, Meal, MealItem

LOG_MEAL_SYSTEM = """You turn a short message about food someone ate into structured data.
- One entry per distinct food or drink. Keep names short, in the language of the message.
- Estimate grams and macros (kcal, protein, carbohydrates, fat) for the stated portion;
  assume a typical portion when none is given.
- meal_type only when the message says it or the time makes it obvious.
- eaten_at only when the message states a clock time; 24-hour HH:MM.
- confidence: high when amounts are explicit, low when you had to guess most of it.
- If the message is not about food or drink that was consumed, return an empty items list."""


def _user_prompt(text: str, now: datetime, zone: ZoneInfo) -> str:
    local = now.astimezone(zone)
    return f"Local time now: {local:%Y-%m-%d %H:%M} ({zone.key}).\nMessage: {text}"


class LogMeal:
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
        async with self._uow.for_user(request.user_id) as uow:
            profile = await uow.repo(ProfileRepository).get(request.user_id)
        locale = profile.locale or self._default_locale
        now = self._clock.now()
        try:
            extraction = await self._llm.structured(
                task=LLMTask.FAST,
                system=LOG_MEAL_SYSTEM,
                user=_user_prompt(request.text, now, profile.timezone),
                schema=MealExtraction,
            )
        except LLMInvalidOutput:
            return SkillResult(output=self._tr.t("nutrition.log_meal.not_understood", locale))
        except LLMError:
            return SkillResult(output=self._tr.t("nutrition.errors.llm_unavailable", locale))
        if not extraction.items:
            return SkillResult(output=self._tr.t("nutrition.log_meal.not_understood", locale))
        meal = Meal.from_items(
            recorded_at=resolve_eaten_at(now, profile.timezone, extraction.eaten_time()),
            items=tuple(
                MealItem(
                    name=i.name,
                    amount_g=i.amount_g,
                    macros=Macros(
                        kcal=i.kcal, protein_g=i.protein_g, carbs_g=i.carbs_g, fat_g=i.fat_g
                    ),
                )
                for i in extraction.items
            ),
            meal_type=extraction.meal_type,
            source=CHAT_SOURCE,
        )
        async with self._uow.for_user(request.user_id) as uow:
            stored = await uow.repo(MealRepository).add(request.user_id, meal)
        output = meal_confirmation(
            stored, confidence=extraction.confidence, locale=locale, tr=self._tr
        )
        # The meal is already committed; memory is best-effort through its port.
        with suppress(Exception):
            await self._memory.upsert(
                user_id=request.user_id,
                agent="nutrition",
                key=request.task_id,
                text=output,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(
            output=output, log_entry=request.text, log_recorded_at=stored.recorded_at
        )
