from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from orchestrator.application.ports import ChatTaskRepository, PendingActionRepository, RunContext
from orchestrator.application.proposals import RecordProposals
from orchestrator.testing import in_memory_uow
from shared.a2a.proposals import Proposal
from shared.testing.fakes import FixedClock


async def setup():
    now = datetime(2026, 10, 14, tzinfo=UTC)
    uow = in_memory_uow(FixedClock(now))
    user = uuid4()
    async with uow.for_user(user) as tx:
        task = await tx.repo(ChatTaskRepository).create(
            user, lead_agent=None, title=None, household_id=None
        )
    return uow, RunContext(user, task.id, None, None, ZoneInfo("UTC"), "en", now)


async def test_record_expires_previous_proposal_and_preserves_home_household():
    uow, ctx = await setup()
    recorder = RecordProposals(uow, ttl=timedelta(minutes=5))
    old = await recorder.record(
        ctx, "calendar", Proposal("calendar.delete", "Delete?", {"event_id": "one"})
    )
    household = uuid4()
    current = await recorder.record(
        ctx,
        "home",
        Proposal(
            "home.call_tool", "Turn off?", {"household_id": str(household), "tool": "LightOff"}
        ),
    )
    assert current.household_id == household
    assert current.task_id == ctx.task_id
    assert current.expires_at == ctx.now + timedelta(minutes=5)
    async with uow.for_user(ctx.user_id) as tx:
        repo = tx.repo(PendingActionRepository)
        assert await repo.pending(ctx.user_id, ctx.task_id) == current
        assert (await repo.claim(ctx.user_id, ctx.task_id, old.id, "confirm")).reason == "expired"
        assert await repo.pending(uuid4(), ctx.task_id) is None


@pytest.mark.parametrize(
    ("agent", "action"),
    [("home", "calendar.delete"), ("calendar", "home.call_tool"), ("sleep", "home.call_tool")],
)
async def test_recorder_rejects_agent_action_mismatch(agent, action):
    uow, ctx = await setup()
    with pytest.raises(ValueError, match="invalid_proposal"):
        await RecordProposals(uow, ttl=timedelta(minutes=5)).record(
            ctx, agent, Proposal(action, "Change?", {})
        )
    async with uow.for_user(ctx.user_id) as tx:
        assert await tx.repo(PendingActionRepository).pending(ctx.user_id, ctx.task_id) is None
