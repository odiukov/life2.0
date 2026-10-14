"""coach_session: summarize a finished coaching transcript and store it as a mood entry."""

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

from mood.application.schemas import MoodExtraction
from mood.domain.entry import MoodEntry

SYSTEM = """You read a finished coaching-session transcript between a coach and a person.
- summary: three short plain-text lines on what the person worked through, in the transcript's language.
- mood_score, energy, stress (1–10), valence and tags describe the person at the end of the session;
  prefer null over guessing."""


class CoachSession:
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
        transcript = request.params.get("transcript")
        text = transcript if isinstance(transcript, str) and transcript.strip() else request.text
        async with self._uow.for_user(uid) as tx:
            settings = await tx.repo(UserSettingsRepository).get(uid)
        locale = settings.locale or self._default_locale
        try:
            extracted = await self._llm.structured(
                task=LLMTask.SMART, system=SYSTEM, user=text, schema=MoodExtraction
            )
        except LLMInvalidOutput:
            extracted = None
        except LLMError:
            return SkillResult(
                output=self._tr.t("analysis.errors.llm_unavailable", locale), failed=True
            )
        now = self._clock.now()
        entry = MoodEntry(
            recorded_at=now,
            mood_score=extracted.mood_score if extracted else None,
            energy=extracted.energy if extracted else None,
            stress=extracted.stress if extracted else None,
            valence=extracted.valence if extracted else None,
            tags=tuple(extracted.tags) if extracted else (),
            raw_text=text,
            source_skill="coach_session",
            source="mood_agent",
        )
        async with self._uow.for_user(uid) as tx:
            await tx.repo(HealthLogRepository).add(
                uid,
                HealthLogRow(
                    type="mood",
                    recorded_at=now,
                    data=entry.to_data(),
                    source="mood_agent",
                    agent="mood",
                ),
            )
        output = (
            self._tr.t("mood.coach.summary", locale, summary=extracted.summary)
            if extracted
            else self._tr.t("mood.coach.saved", locale)
        )
        with suppress(Exception):
            await self._memory.upsert(
                user_id=uid,
                agent="mood",
                key=request.task_id,
                text=output,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(output=output)
