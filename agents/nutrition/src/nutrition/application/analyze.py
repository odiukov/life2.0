"""Nutrition analysis and recommendations: nutrition's data on the shared analysis pipeline."""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime

from shared.a2a.request import SkillRequest
from shared.analysis.skill import AnalysisData, AnalysisSkill, AnalysisSpec, LoadedData, same_day
from shared.domain.energy import calorie_goal
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.peers import PeerClient
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork, UnitOfWorkFactory
from shared.ports.users import UserSettings
from shared.ports.vector_memory import VectorMemory

from nutrition.application.peers import PEER_SKILLS
from nutrition.application.ports import (
    BodyMetricsRepository,
    MealRepository,
    NutritionSync,
    ProfileRepository,
)
from nutrition.application.prompts import PEER_ORDER, SKILL_TAIL, AnalysisMode, analysis_sections
from nutrition.domain.day import day_window, local_today
from nutrition.domain.meal import total_intake

RECENT_MEALS = 10

NUTRITION_SPEC = AnalysisSpec(
    agent="nutrition",
    tails={str(mode): tail for mode, tail in SKILL_TAIL.items()},
    peer_order=PEER_ORDER,
    peer_skills=PEER_SKILLS,
    peer_date=same_day,
    focus_on_peer_date=False,  # nutrition already analyses request.for_date as its day
    error_key="nutrition.errors.llm_unavailable",
)


class NutritionAnalysisData(AnalysisData):
    def __init__(self, sync: NutritionSync) -> None:
        self._sync = sync

    async def prepare(self, request: SkillRequest) -> None:
        with suppress(Exception):
            await self._sync.refresh(request.user_id)

    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData:
        uid = request.user_id
        profile = await uow.repo(ProfileRepository).get(uid)
        today = local_today(now, profile.timezone)
        day = request.for_date or today
        start, end = day_window(day, profile.timezone)
        meals = await uow.repo(MealRepository).between(uid, start, end)
        recent = await uow.repo(MealRepository).recent(uid, RECENT_MEALS)
        body = await uow.repo(BodyMetricsRepository).latest(uid)
        goal = calorie_goal(
            profile.body,
            measured_bmr_kcal=body.bmr_kcal if body else None,
            weight_kg=body.weight_kg if body else None,
        )
        return LoadedData(
            analysis_sections(
                day=day,
                is_today=day == today,
                zone=profile.timezone,
                profile=profile.body,
                intake=total_intake(meals),
                goal=goal,
                recent=recent,
                body=body,
            )
        )


class AnalyzeNutrition(AnalysisSkill):
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
        super().__init__(
            spec=NUTRITION_SPEC,
            mode=mode,
            data=NutritionAnalysisData(sync),
            llm=llm,
            uow=uow,
            peers=peers,
            memory=memory,
            clock=clock,
            translator=translator,
            default_locale=default_locale,
        )
