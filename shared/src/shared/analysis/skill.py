"""AnalysisSkill: load → peers → memories → prompt → model → memory, the same for every health agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.analysis.prompt import PromptInputs, PromptSection, compose_prompt
from shared.ports.clock import Clock
from shared.ports.llm import LLMError, LLMProvider, LLMTask
from shared.ports.peers import PeerClient
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork, UnitOfWorkFactory
from shared.ports.users import UserSettings, UserSettingsRepository
from shared.ports.vector_memory import VectorMemory

MEMORY_LIMIT = 5
PeerDate = Callable[[SkillRequest, date], date | None]


def same_day(request: SkillRequest, today: date) -> date | None:
    return request.for_date


def previous_day(request: SkillRequest, today: date) -> date | None:
    """Sleep: last night was shaped by yesterday's training and food."""
    return today - timedelta(days=1)


@dataclass(frozen=True, slots=True)
class AnalysisSpec:
    agent: str
    tails: Mapping[str, str]
    peer_order: tuple[str, ...]
    peer_skills: Mapping[str, str]
    peer_date: PeerDate = same_day
    memories: bool = True
    focus_on_peer_date: bool = True
    llm_task: LLMTask = LLMTask.SMART
    error_key: str = "analysis.errors.llm_unavailable"


@dataclass(frozen=True, slots=True)
class LoadedData:
    sections: Sequence[PromptSection]
    tail_override: str | None = None
    answer: str | None = None  # a final, already localized reply: skip peers, model and memory


class AnalysisData(ABC):
    async def prepare(self, request: SkillRequest) -> None:  # noqa: B027 - optional hook
        """Work outside the transaction (e.g. ask a sync service to refresh). Must not raise."""

    @abstractmethod
    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData: ...


@dataclass
class AnalysisSkill:
    spec: AnalysisSpec
    mode: str
    data: AnalysisData
    llm: LLMProvider
    uow: UnitOfWorkFactory
    peers: PeerClient
    memory: VectorMemory
    clock: Clock
    translator: Translator
    default_locale: str

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        with suppress(Exception):
            await self.data.prepare(request)
        now = self.clock.now()
        uid = request.user_id
        async with self.uow.for_user(uid) as tx:
            settings = await tx.repo(UserSettingsRepository).get(uid)
            loaded = await self.data.load(tx, request, settings, now)
        if loaded.answer is not None:
            return SkillResult(output=loaded.answer)
        today = settings.today(now)
        wanted = {
            name: self.spec.peer_skills[name] for name in consult if name in self.spec.peer_skills
        }
        answers: dict[str, str] = {}
        if wanted:
            with suppress(Exception):
                fetched = await self.peers.fetch_artifacts(
                    user_id=uid, wanted=wanted, for_date=self.spec.peer_date(request, today)
                )
                answers = {name: fetched[name] for name in wanted if fetched.get(name, "").strip()}
        memories: list[str] | None = None
        if self.spec.memories:
            memories = []
            with suppress(Exception):
                memories = [
                    m.text
                    for m in await self.memory.search(
                        user_id=uid, query=self.mode, limit=MEMORY_LIMIT
                    )
                ]
        focus = (
            request.for_date if (self.spec.focus_on_peer_date and request.is_peer_call) else None
        )
        system, user = compose_prompt(
            PromptInputs(
                agent=self.spec.agent,
                mode=self.mode,
                sections=loaded.sections,
                peers=answers,
                peer_order=self.spec.peer_order,
                memories=memories,
                message=request.text,
                tail=loaded.tail_override or self.spec.tails[self.mode],
                focus_date=focus,
            )
        )
        try:
            output = await self.llm.text(task=self.spec.llm_task, system=system, user=user)
        except LLMError:
            locale = settings.locale or self.default_locale
            return SkillResult(output=self.translator.t(self.spec.error_key, locale), failed=True)
        with suppress(Exception):
            await self.memory.upsert(
                user_id=uid,
                agent=self.spec.agent,
                key=request.task_id,
                text=output,
                metadata={"skill": request.skill_id},
            )
        return SkillResult(
            output=output, consulted=tuple(name for name in wanted if name in answers)
        )
