"""log_sleep: free text → a stored chat sleep_session (the legacy skill stored nothing)."""

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

from sleep.application.schemas import SleepExtraction
from sleep.domain.session import SleepSession, resolve_session

SYSTEM = """You turn a short message about last night's sleep into structured data.
- duration_minutes: only when the person states how long they slept ("7 часов" → 420, "6.5h" → 390).
- bed_time / wake_time: 24-hour HH:MM only when stated ("лёг в 23:30", "встал в 7" → 07:00).
- quality: 1–5 only when they rate it or clearly say good or bad (great=5, ok=3, terrible=1).
- Leave every field null when it is not stated. Never invent times."""


class LogSleep:
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
            night = await self._llm.structured(
                task=LLMTask.FAST, system=SYSTEM, user=request.text, schema=SleepExtraction
            )
        except LLMInvalidOutput:
            return SkillResult(output=self._tr.t("sleep.log.not_understood", locale))
        except LLMError:
            return SkillResult(
                output=self._tr.t("analysis.errors.llm_unavailable", locale), failed=True
            )
        placed = resolve_session(night, self._clock.now(), settings.timezone)
        if placed is None:
            return SkillResult(output=self._tr.t("sleep.log.not_understood", locale))
        start_utc, end_utc = placed
        start, end = start_utc.astimezone(settings.timezone), end_utc.astimezone(settings.timezone)
        seconds = int((end_utc - start_utc).total_seconds())
        session = SleepSession(
            start=start,
            end=end,
            duration_s=seconds,
            deep_s=None,
            rem_s=None,
            light_s=None,
            awake_s=None,
            score=None,
            hrv=None,
            avg_hr=None,
            quality=night.quality,
            source="chat",
        )
        async with self._uow.for_user(uid) as tx:
            stored_at = await tx.repo(HealthLogRepository).add(
                uid,
                HealthLogRow(
                    type="sleep_session",
                    recorded_at=start_utc,
                    data=session.to_data(),
                    source="chat",
                    agent="sleep",
                ),
            )
        hours = round(seconds / 3600, 1)
        count: int | float = int(hours) if hours.is_integer() else hours
        n = self._tr.number(hours, locale, digits=0 if hours.is_integer() else 1)
        output = self._tr.t(
            "sleep.log.confirmed",
            locale,
            start=start.strftime("%H:%M"),
            end=end.strftime("%H:%M"),
            hours=self._tr.t("sleep.hours", locale, count=count, n=n),
        )
        if night.quality is not None:
            output += self._tr.t("sleep.log.quality", locale, quality=night.quality)
        with suppress(Exception):
            await self._memory.upsert(
                user_id=uid,
                agent="sleep",
                key=request.task_id,
                text=output,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(output=output, log_entry=request.text, log_recorded_at=stored_at)
