from __future__ import annotations

from contextlib import suppress

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.domain.energy import calorie_goal
from shared.ports.clock import Clock
from shared.ports.llm import LLMError, LLMProvider, LLMTask
from shared.ports.peers import PeerClient
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.vector_memory import VectorMemory

from nutrition.application.peers import PEER_SKILLS
from nutrition.application.ports import (
    BodyMetricsRepository,
    MealRepository,
    NutritionSync,
    ProfileRepository,
)
from nutrition.application.prompts import AnalysisInputs, AnalysisMode, build_analysis_prompt
from nutrition.domain.day import day_window, local_today
from nutrition.domain.meal import total_intake

RECENT_MEALS = 10
MEMORIES = 5


class AnalyzeNutrition:
    def __init__(
        self,
        *,
        mode: AnalysisMode,
        llm: LLMProvider,
        uow: UnitOfWorkFactory,
        clock: Clock,
        translator: Translator,
        peers: PeerClient,
        memory: VectorMemory,
        sync: NutritionSync,
        default_locale: str,
    ) -> None:
        self._mode: AnalysisMode = mode
        self._llm = llm
        self._uow = uow
        self._clock = clock
        self._tr = translator
        self._peers = peers
        self._memory = memory
        self._sync = sync
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        with suppress(Exception):
            await self._sync.refresh()
        now = self._clock.now()
        uid = request.user_id
        async with self._uow.for_user(uid) as uow:
            profile = await uow.repo(ProfileRepository).get(uid)
            today = local_today(now, profile.timezone)
            day = request.for_date or today
            start, end = day_window(day, profile.timezone)
            meals = await uow.repo(MealRepository).between(uid, start, end)
            recent = await uow.repo(MealRepository).recent(uid, RECENT_MEALS)
            body = await uow.repo(BodyMetricsRepository).latest(uid)
        wanted = {name: PEER_SKILLS[name] for name in consult if name in PEER_SKILLS}
        # PeerClient omits failures and applies its own deadline. Defend against
        # unexpected implementation errors while preserving task cancellation.
        peers: dict[str, str] = {}
        if wanted:
            with suppress(Exception):
                answers = await self._peers.fetch_artifacts(
                    user_id=uid, wanted=wanted, for_date=request.for_date
                )
                peers = {
                    name: answers[name]
                    for name in wanted
                    if name in answers and answers[name].strip()
                }
        memories: list[str] = []
        with suppress(Exception):
            memories = [
                memory.text
                for memory in await self._memory.search(
                    user_id=uid, query=self._mode, limit=MEMORIES
                )
            ]
        goal = calorie_goal(
            profile.body,
            measured_bmr_kcal=body.bmr_kcal if body else None,
            weight_kg=body.weight_kg if body else None,
        )
        system, user = build_analysis_prompt(
            AnalysisInputs(
                mode=self._mode,
                day=day,
                is_today=day == today,
                zone=profile.timezone,
                profile=profile.body,
                intake=total_intake(meals),
                goal=goal,
                recent=recent,
                body=body,
                peers=peers,
                memories=memories,
                message=request.text,
            )
        )
        try:
            output = await self._llm.text(task=LLMTask.SMART, system=system, user=user)
        except LLMError:
            locale = profile.locale or self._default_locale
            return SkillResult(output=self._tr.t("nutrition.errors.llm_unavailable", locale))
        with suppress(Exception):
            await self._memory.upsert(
                user_id=uid,
                agent="nutrition",
                key=request.task_id,
                text=output,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(output=output, consulted=tuple(name for name in wanted if name in peers))
