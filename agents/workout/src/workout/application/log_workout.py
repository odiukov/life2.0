"""log_workout: free text → a stored chat `activity` row (the legacy skill stored nothing)."""

from __future__ import annotations

from contextlib import suppress

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.llm import LLMError, LLMInvalidOutput, LLMProvider, LLMTask
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.ports.vector_memory import VectorMemory

from workout.application.schemas import WorkoutExtraction
from workout.domain.workout import Workout, resolve_start

SYSTEM = """You turn a short message about a workout the person did into structured data.
- activity_type: running, cycling, walking, swimming, strength_training, yoga, hiking or other.
- duration_minutes: the stated duration; if only distance and pace are given, compute it.
- distance_km only when stated; effort 1–10 only when they rate how hard it was.
- started_at: 24-hour HH:MM only when they say when it started.
If the message is not about a completed workout, use activity_type "other" and duration_minutes 1, and set name to "none"."""


class LogWorkout:
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
            settings = await tx.repo(UserSettingsRepository).get(uid)
        locale = settings.locale or self._default_locale
        try:
            extracted = await self._llm.structured(
                task=LLMTask.FAST, system=SYSTEM, user=request.text, schema=WorkoutExtraction
            )
        except LLMInvalidOutput:
            return SkillResult(output=self._tr.t("workout.log.not_understood", locale))
        except LLMError:
            return SkillResult(
                output=self._tr.t("analysis.errors.llm_unavailable", locale), failed=True
            )
        if extracted.name == "none":
            return SkillResult(output=self._tr.t("workout.log.not_understood", locale))
        start = resolve_start(
            extracted.started_at, extracted.duration_minutes, self._clock.now(), settings.timezone
        )
        workout = Workout(
            recorded_at=start,
            activity_type=extracted.activity_type,
            name=extracted.name or extracted.activity_type,
            duration_s=extracted.duration_minutes * 60,
            distance_m=extracted.distance_km * 1000 if extracted.distance_km is not None else None,
            calories=None,
            avg_hr=None,
            max_hr=None,
            effort=extracted.effort,
            source="chat",
        )
        async with self._uow.for_user(uid) as tx:
            stored_at = await tx.repo(HealthLogRepository).add(
                uid,
                HealthLogRow(
                    type="activity",
                    recorded_at=start,
                    data=workout.to_data(),
                    source="chat",
                    agent="workout",
                ),
            )
        distance = ""
        if extracted.distance_km is not None:
            km = extracted.distance_km
            distance = self._tr.t(
                "workout.log.distance",
                locale,
                km=self._tr.number(km, locale, digits=0 if float(km).is_integer() else 1),
            )
        output = self._tr.t(
            "workout.log.confirmed",
            locale,
            activity=self._tr.t(f"workout.activity.{extracted.activity_type}", locale),
            minutes=extracted.duration_minutes,
            distance=distance,
        )
        with suppress(Exception):
            await self._memory.upsert(
                user_id=uid,
                agent="workout",
                key=request.task_id,
                text=output,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(output=output, log_entry=request.text, log_recorded_at=stored_at)
