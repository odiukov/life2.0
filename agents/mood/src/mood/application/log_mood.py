"""log_mood: free text → a mood entry; the raw words are kept even when the scores are unreadable."""

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
from mood.domain.entry import MoodEntry, has_signal

SYSTEM = """You extract how a person feels from one short message.
- mood_score, energy, stress: integers 1–10 only when the text supports them; prefer null over guessing.
- valence: pos, neu or neg when the feeling has a clear direction.
- tags: short lowercase descriptors in the language of the message ("усталость", "focused"), at most 6.
- summary: a one-line paraphrase; if the message expresses no mood or feeling, every field null,
  tags empty and summary "no mood signal"."""


def _source(request: SkillRequest) -> str:
    value = request.params.get("source")
    return value if isinstance(value, str) and value else "manual"


class LogMood:
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

    async def _extract(self, text: str) -> MoodExtraction | None:
        try:
            return await self._llm.structured(
                task=LLMTask.FAST, system=SYSTEM, user=text, schema=MoodExtraction
            )
        except LLMInvalidOutput as first:
            repair = f"{text}\n\n---\nYour previous answer was rejected:\n{first.reason}\nReturn a valid answer."
            try:
                return await self._llm.structured(
                    task=LLMTask.FAST, system=SYSTEM, user=repair, schema=MoodExtraction
                )
            except LLMInvalidOutput:
                return None

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        uid = request.user_id
        async with self._uow.for_user(uid) as tx:
            settings = await tx.repo(UserSettingsRepository).get(uid)
        locale = settings.locale or self._default_locale
        try:
            extracted = await self._extract(request.text)
        except LLMError:
            return SkillResult(
                output=self._tr.t("analysis.errors.llm_unavailable", locale), failed=True
            )
        if extracted is not None and not has_signal(extracted):
            return SkillResult(output=self._tr.t("mood.log.no_signal", locale))
        now = self._clock.now()
        entry = MoodEntry(
            recorded_at=now,
            mood_score=extracted.mood_score if extracted else None,
            energy=extracted.energy if extracted else None,
            stress=extracted.stress if extracted else None,
            valence=extracted.valence if extracted else None,
            tags=tuple(extracted.tags) if extracted else (),
            raw_text=request.text,
            source_skill="log_mood" if extracted else "log_mood_fallback",
            source=_source(request),
        )
        async with self._uow.for_user(uid) as tx:
            stored_at = await tx.repo(HealthLogRepository).add(
                uid,
                HealthLogRow(
                    type="mood",
                    recorded_at=now,
                    data=entry.to_data(),
                    source=entry.source,
                    agent="mood",
                ),
            )
        if extracted is None:
            output = self._tr.t("mood.log.saved_raw", locale)
        else:
            tags = (
                self._tr.t("mood.log.tags", locale, tags=", ".join(entry.tags))
                if entry.tags
                else ""
            )
            key = (
                "mood.log.confirmed_score" if entry.mood_score is not None else "mood.log.confirmed"
            )
            output = self._tr.t(key, locale, score=entry.mood_score or "", tags=tags)
        with suppress(Exception):
            await self._memory.upsert(
                user_id=uid,
                agent="mood",
                key=request.task_id,
                text=request.text,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(output=output, log_entry=request.text, log_recorded_at=stored_at)
