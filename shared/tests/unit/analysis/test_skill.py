from dataclasses import replace
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.analysis.prompt import PromptSection
from shared.analysis.skill import (
    AnalysisData,
    AnalysisSkill,
    AnalysisSpec,
    LoadedData,
    previous_day,
    same_day,
)
from shared.config import find_locales_dir
from shared.ports.llm import LLMTask, LLMUnavailable
from shared.ports.uow import UnitOfWork
from shared.ports.users import UserSettings, UserSettingsRepository
from shared.testing.fakes import (
    FakeLLM,
    FakePeerClient,
    FixedClock,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
    InMemoryVectorMemory,
)

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
SPEC = AnalysisSpec(
    agent="sleep",
    tails={"analyze_sleep": "TAIL"},
    peer_order=("workout", "mood"),
    peer_skills={"workout": "analyze_workout", "mood": "analyze_mood"},
    peer_date=previous_day,
)


class Data(AnalysisData):
    def __init__(self, override: str | None = None) -> None:
        self.override = override
        self.prepared = 0

    async def prepare(self, request: SkillRequest) -> None:
        self.prepared += 1

    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData:
        return LoadedData(
            [PromptSection("Recent sleep", f"today={settings.today(now)}")],
            tail_override=self.override,
        )


def req(**kw: object) -> SkillRequest:
    values: dict[str, object] = {
        "task_id": "t1",
        "context_id": "c",
        "text": "как сплю?",
        "user_id": uuid4(),
        "skill_id": "analyze_sleep",
        "for_date": None,
        "is_peer_call": False,
    }
    values.update(kw)
    return SkillRequest(**values)  # type: ignore[arg-type]


def skill(
    llm: FakeLLM,
    peers: FakePeerClient | None = None,
    memory: InMemoryVectorMemory | None = None,
    data: Data | None = None,
    spec: AnalysisSpec = SPEC,
) -> tuple[AnalysisSkill, InMemoryUserSettings]:
    users = InMemoryUserSettings()
    return AnalysisSkill(
        spec=spec,
        mode="analyze_sleep",
        data=data or Data(),
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({UserSettingsRepository: users}),
        peers=peers or FakePeerClient(),
        memory=memory or InMemoryVectorMemory(),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="ru",
    ), users


async def test_full_flow_consults_yesterday_and_records_memory() -> None:
    llm = FakeLLM()
    llm.queue_text("Сон стабильный.")
    peers = FakePeerClient({"workout": "ran 10k", "mood": ""})
    memory = InMemoryVectorMemory()
    handler, users = skill(llm, peers, memory)
    request = req()
    users.seed(request.user_id, timezone="Europe/Lisbon", locale="ru")
    result = await handler(request, ("workout", "mood", "unknown"))
    assert result.output == "Сон стабильный."
    assert result.consulted == ("workout",)
    assert peers.calls[0]["wanted"] == {"workout": "analyze_workout", "mood": "analyze_mood"}
    assert peers.calls[0]["for_date"] == date(2026, 10, 12)
    call = llm.calls[0]
    assert call.task is LLMTask.SMART
    assert "today=2026-10-13" in call.user
    assert "### workout\nran 10k" in call.user
    assert memory.items[0][1:3] == ("sleep", "t1")


async def test_no_consult_means_no_peer_call() -> None:
    llm = FakeLLM()
    llm.queue_text("ok")
    peers = FakePeerClient({"workout": "x"})
    handler, _ = skill(llm, peers)
    await handler(req(), ())
    assert peers.calls == []


async def test_peer_and_memory_failures_do_not_break_the_skill() -> None:
    class Broken(FakePeerClient):
        async def fetch_artifacts(self, **kw):  # type: ignore[no-untyped-def, override]
            raise RuntimeError("down")

    class BrokenMemory(InMemoryVectorMemory):
        async def search(self, **kw):  # type: ignore[no-untyped-def, override]
            raise RuntimeError("qdrant down")

        async def upsert(self, **kw):  # type: ignore[no-untyped-def, override]
            raise RuntimeError("qdrant down")

    llm = FakeLLM()
    llm.queue_text("ok")
    handler, _ = skill(llm, Broken(), BrokenMemory())
    result = await handler(req(), ("workout",))
    assert result.output == "ok"
    assert result.consulted == ()
    assert "## Memories\nNo relevant memories." in llm.calls[0].user


async def test_model_down_is_a_localized_failure() -> None:
    llm = FakeLLM()
    llm.queue_text(LLMUnavailable("down"))
    memory = InMemoryVectorMemory()
    handler, users = skill(llm, memory=memory)
    request = req()
    users.seed(request.user_id, locale="en")
    result = await handler(request, ())
    assert result.failed
    assert result.output.startswith("I can't answer right now")
    assert memory.items == []


async def test_tail_override_and_prepare_and_peer_focus() -> None:
    llm = FakeLLM()
    llm.queue_text("ok")
    data = Data(override="Not enough data — ask the user to log first.")
    handler, _ = skill(llm, data=data)
    await handler(req(is_peer_call=True, for_date=date(2026, 10, 10)), ())
    assert data.prepared == 1
    assert llm.calls[0].user.endswith("Not enough data — ask the user to log first.")
    assert "## Peer-consult focus date: 2026-10-10" in llm.calls[0].user


async def test_a_final_answer_skips_peers_and_model() -> None:
    class Done(Data):
        async def load(self, uow, request, settings, now):  # type: ignore[no-untyped-def, override]
            return LoadedData([], answer="Нет активных лекарств.")

    llm = FakeLLM()
    peers = FakePeerClient({"workout": "x"})
    memory = InMemoryVectorMemory()
    handler, _ = skill(llm, peers, memory, data=Done())
    result = await handler(req(), ("workout",))
    assert (result.output, result.failed, result.consulted) == ("Нет активных лекарств.", False, ())
    assert llm.calls == []
    assert peers.calls == []
    assert memory.items == []


def test_peer_dates() -> None:
    today = date(2026, 10, 13)
    assert same_day(req(for_date=date(2026, 10, 1)), today) == date(2026, 10, 1)
    assert same_day(req(), today) is None
    assert previous_day(req(), today) == date(2026, 10, 12)


async def test_disabled_memories_skip_search_and_focus() -> None:
    class NoSearch(InMemoryVectorMemory):
        async def search(self, **kw):  # type: ignore[no-untyped-def, override]
            pytest.fail("memory search must be disabled")

    llm = FakeLLM()
    llm.queue_text("ok")
    memory = NoSearch()
    handler, _ = skill(
        llm, memory=memory, spec=replace(SPEC, memories=False, focus_on_peer_date=False)
    )
    await handler(req(is_peer_call=True, for_date=date(2026, 10, 10)), ())
    assert "## Memories" not in llm.calls[0].user
    assert "## Peer-consult focus date" not in llm.calls[0].user
    assert len(memory.items) == 1


async def test_unexpected_model_errors_reach_executor_without_memory_write() -> None:
    llm = FakeLLM()
    llm.queue_text(RuntimeError("unexpected"))
    memory = InMemoryVectorMemory()
    handler, _ = skill(llm, memory=memory)
    with pytest.raises(RuntimeError, match="unexpected"):
        await handler(req(), ())
    assert memory.items == []
