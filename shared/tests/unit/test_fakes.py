from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import BaseModel
from shared.ports.llm import LLMInvalidOutput, LLMProvider, LLMTask, LLMUnavailable
from shared.ports.peers import PeerClient
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.vector_memory import VectorMemory
from shared.testing.fakes import (
    FakeLLM,
    FakePeerClient,
    FixedClock,
    InMemoryUnitOfWorkFactory,
    InMemoryVectorMemory,
)


class Echo(BaseModel):
    word: str


async def test_fake_llm_returns_queued_structured_and_records_calls() -> None:
    llm: LLMProvider = FakeLLM()
    assert isinstance(llm, FakeLLM)
    llm.queue_structured({"word": "hi"})
    result = await llm.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)
    assert result == Echo(word="hi")
    assert llm.calls[0].task is LLMTask.FAST
    assert llm.calls[0].schema is Echo


async def test_fake_llm_invalid_payload_raises_invalid_output() -> None:
    llm = FakeLLM()
    llm.queue_structured({"nope": 1})
    with pytest.raises(LLMInvalidOutput):
        await llm.structured(task=LLMTask.FAST, system="s", user="u", schema=Echo)


async def test_fake_llm_raises_queued_exception() -> None:
    llm = FakeLLM()
    llm.queue_text(LLMUnavailable("down"))
    with pytest.raises(LLMUnavailable):
        await llm.text(task=LLMTask.SMART, system="s", user="u")


def test_fixed_clock_is_tz_aware_and_advances() -> None:
    clock = FixedClock(datetime(2026, 10, 13, 12, 0, tzinfo=UTC))
    assert clock.now().tzinfo is not None
    clock.advance(seconds=90)
    assert clock.now() == datetime(2026, 10, 13, 12, 1, 30, tzinfo=UTC)


def test_fixed_clock_normalizes_constructor_time_to_utc() -> None:
    clock = FixedClock(datetime(2026, 10, 13, 14, 0, tzinfo=timezone(timedelta(hours=2))))
    assert clock.now() == datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    assert clock.now().tzinfo is UTC


def test_fixed_clock_rejects_naive_constructor_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(datetime(2026, 10, 13, 12, 0))


def test_fixed_clock_normalizes_set_time_to_utc() -> None:
    clock = FixedClock(datetime(2026, 10, 13, 12, 0, tzinfo=UTC))
    clock.set(datetime(2026, 10, 13, 14, 0, tzinfo=timezone(timedelta(hours=2))))
    assert clock.now() == datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    assert clock.now().tzinfo is UTC


def test_fixed_clock_rejects_naive_set_time() -> None:
    clock = FixedClock(datetime(2026, 10, 13, 12, 0, tzinfo=UTC))
    with pytest.raises(ValueError, match="timezone-aware"):
        clock.set(datetime(2026, 10, 13, 14, 0))


async def test_in_memory_uow_commits_and_rolls_back() -> None:
    class Notes:
        def __init__(self) -> None:
            self.items: list[str] = []

    notes = Notes()
    factory: UnitOfWorkFactory = InMemoryUnitOfWorkFactory({Notes: notes})
    assert isinstance(factory, InMemoryUnitOfWorkFactory)
    user = uuid4()
    async with factory.for_user(user) as uow:
        uow.repo(Notes).items.append("a")
    with pytest.raises(RuntimeError):
        async with factory.for_user(user):
            raise RuntimeError("boom")
    assert factory.commits == [user]
    assert factory.rollbacks == [user]
    assert notes.items == ["a"]


async def test_in_memory_vector_memory_filters_by_user_and_agent() -> None:
    memory: VectorMemory = InMemoryVectorMemory()
    a, b = uuid4(), uuid4()
    await memory.upsert(user_id=a, agent="nutrition", key="1", text="oats", metadata={})
    await memory.upsert(user_id=b, agent="nutrition", key="2", text="eggs", metadata={})
    found = await memory.search(user_id=a, query="x", limit=5)
    assert [m.text for m in found] == ["oats"]


async def test_in_memory_vector_memory_upsert_scopes_keys_to_user_and_agent() -> None:
    memory = InMemoryVectorMemory()
    user_a, user_b = uuid4(), uuid4()
    await memory.upsert(user_id=user_a, agent="nutrition", key="shared", text="old", metadata={})
    await memory.upsert(
        user_id=user_b, agent="nutrition", key="shared", text="other user", metadata={}
    )
    await memory.upsert(
        user_id=user_a, agent="sleep", key="shared", text="other agent", metadata={}
    )
    await memory.upsert(
        user_id=user_a, agent="nutrition", key="shared", text="updated", metadata={}
    )

    user_a_results = await memory.search(user_id=user_a, query="x", limit=5)
    user_b_results = await memory.search(user_id=user_b, query="x", limit=5)
    sleep_results = await memory.search(user_id=user_a, query="x", limit=5, agents=["sleep"])
    assert [(item.agent, item.text) for item in user_a_results] == [
        ("sleep", "other agent"),
        ("nutrition", "updated"),
    ]
    assert [(item.agent, item.text) for item in user_b_results] == [("nutrition", "other user")]
    assert [(item.agent, item.text) for item in sleep_results] == [("sleep", "other agent")]


async def test_fake_peer_client_returns_only_scripted_peers() -> None:
    peers: PeerClient = FakePeerClient({"workout": "ran 5k"})
    assert isinstance(peers, FakePeerClient)
    got = await peers.fetch_artifacts(
        user_id=uuid4(), wanted={"workout": "analyze_workout", "sleep": "analyze_sleep"}
    )
    assert got == {"workout": "ran 5k"}
    assert peers.calls[0]["wanted"] == {"workout": "analyze_workout", "sleep": "analyze_sleep"}
