from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from shared.a2a.proposals import Proposal
from shared.ports.uow import UnitOfWorkFactory

from orchestrator.application.ports import PendingAction, PendingActionRepository, RunContext


class RecordProposals:
    def __init__(self, uow: UnitOfWorkFactory, *, ttl: timedelta) -> None:
        self._uow, self._ttl = uow, ttl

    async def record(self, ctx: RunContext, agent: str, proposal: Proposal) -> PendingAction:
        allowed = {
            "home": {"home.call_tool"},
            "calendar": {"calendar.create", "calendar.update", "calendar.delete"},
        }
        if proposal.action not in allowed.get(agent, set()):
            raise ValueError("invalid_proposal")
        raw = proposal.payload.get("household_id") if agent == "home" else None
        household = UUID(str(raw)) if raw else None
        async with self._uow.for_user(ctx.user_id) as tx:
            return await tx.repo(PendingActionRepository).propose(
                ctx.user_id,
                ctx.task_id,
                agent=agent,
                kind=proposal.action,
                payload=proposal.payload,
                summary=proposal.summary,
                household_id=household,
                ttl=self._ttl,
            )
