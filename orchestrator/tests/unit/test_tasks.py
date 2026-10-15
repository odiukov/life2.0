from datetime import UTC, datetime
from uuid import uuid4

import pytest
from orchestrator.application.ports import NewMessage, TaskBusy, TranscriptRepository
from orchestrator.application.tasks import NoHousehold, TaskNotFound, Tasks, UnknownAgent
from orchestrator.testing import FakeChatGraph, in_memory_uow
from shared.testing.fakes import FixedClock


class Households:
    household = None

    async def current(self, user):
        return self.household


@pytest.fixture
def env():
    clock = FixedClock(datetime(2026, 10, 14, tzinfo=UTC))
    uow = in_memory_uow(clock)
    households, graph = Households(), FakeChatGraph()
    return (
        Tasks(uow=uow, households=households, graph=graph),
        uow,
        households,
        graph,
        clock,
        uuid4(),
    )


async def test_lead_validation_household_and_title(env):
    tasks, _, households, _, _, user = env
    with pytest.raises(UnknownAgent):
        await tasks.open(user, lead_agent="astrology", title=None)
    with pytest.raises(NoHousehold):
        await tasks.open(user, lead_agent="home", title=None)
    households.household = uuid4()
    task = await tasks.open(user, lead_agent="kitchen", title="a" * 150)
    assert task.household_id == households.household
    assert len(task.title) == 120
    cleared = await tasks.update(user, task.id, {"lead_agent": None})
    assert cleared.lead_agent is cleared.household_id is None
    assert (
        await tasks.update(user, task.id, {"lead_agent": "home"})
    ).household_id == households.household


async def test_read_close_list_and_foreign_access(env):
    tasks, uow, _, graph, clock, user = env
    task = await tasks.open(user, lead_agent=None, title=None)
    async with uow.for_user(user) as tx:
        await tx.repo(TranscriptRepository).append(user, task.id, NewMessage("user", "hello"))
    assert (await tasks.read(user, task.id)).messages[0].text == "hello"
    for action in [tasks.read, tasks.close]:
        with pytest.raises(TaskNotFound):
            await action(uuid4(), task.id)
    with pytest.raises(TaskNotFound):
        await tasks.update(uuid4(), task.id, {"lead_agent": "home"})
    clock.advance(minutes=1)
    newer = await tasks.open(user, lead_agent=None, title=None)
    assert [t.id for t in await tasks.list(user)] == [newer.id, task.id]
    graph.busy = True
    with pytest.raises(TaskBusy):
        await tasks.close(user, task.id)
    assert (await tasks.read(user, task.id)).messages
    graph.busy = False
    await tasks.close(user, task.id)
    with pytest.raises(TaskNotFound):
        await tasks.read(user, task.id)
