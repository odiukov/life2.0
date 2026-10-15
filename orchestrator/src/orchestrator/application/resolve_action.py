from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from shared.observability.logging import get_logger
from shared.ports.skills import SkillCallError, SkillClient, SkillUnavailable
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Calendar, Home

from orchestrator.application.messages import FAILURES, failure
from orchestrator.application.ports import (
    GraphSession,
    PendingActionRepository,
    TranscriptRepository,
)

APPLY = {"calendar": Calendar.APPLY, "home": Home.APPLY}
logger = get_logger(__name__)


class ActionNotFound(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Resolution:
    status: Literal["applying", "applied", "rejected", "expired", "failed"]
    message: str
    code: str | None = None


class ResolveAction:
    def __init__(
        self,
        *,
        uow: UnitOfWorkFactory,
        skills: Callable[[str], SkillClient],
        translator: Translator,
        default_locale: str,
    ) -> None:
        self._uow, self._skills, self._tr, self._default = uow, skills, translator, default_locale

    async def __call__(
        self,
        user_id: UUID,
        task_id: UUID,
        action_id: UUID,
        decision: Literal["confirm", "reject"],
        *,
        session: GraphSession,
    ) -> Resolution:
        async with self._uow.for_user(user_id) as tx:
            locale = (await tx.repo(UserSettingsRepository).get(user_id)).locale or self._default
            claim = await tx.repo(PendingActionRepository).claim(
                user_id, task_id, action_id, decision
            )
            if claim.action is not None:
                await tx.repo(TranscriptRepository).set_action_status(
                    user_id, task_id, action_id, claim.action.status
                )
        if claim.reason == "not_found" or claim.action is None:
            raise ActionNotFound
        action = claim.action
        if claim.reason == "expired":
            result = Resolution("expired", self._tr.t("actions.expired", locale))
        elif claim.reason == "already_decided":
            status = (
                action.status
                if action.status in ("applied", "rejected", "failed", "expired")
                else "applying"
            )
            return Resolution(
                status, self._tr.t("actions.already_decided", locale), action.result_code
            )
        elif claim.reason == "rejected":
            result = Resolution("rejected", self._tr.t("actions.rejected", locale))
        else:
            result = await self._apply(
                user_id, task_id, action.agent, action.id, action.payload, locale
            )
        await session.append(f"[{action.summary} → {result.status}]", result.message)
        return result

    async def _apply(
        self,
        user_id: UUID,
        task_id: UUID,
        agent: str,
        action_id: UUID,
        payload: object,
        locale: str,
    ) -> Resolution:
        code: str | None = None
        try:
            await self._skills(agent).call(
                skill_id=APPLY[agent], user_id=user_id, params={"payload": payload}
            )
        except SkillCallError as exc:
            code = exc.code if exc.code in FAILURES else "generic"
        except SkillUnavailable:
            code = "agent_unavailable"
        except Exception as exc:
            logger.warning("action_apply_failed", agent=agent, error_type=type(exc).__name__)
            code = "generic"
        async with self._uow.for_user(user_id) as tx:
            await tx.repo(PendingActionRepository).finish(
                user_id, action_id, "failed" if code else "applied", code
            )
            await tx.repo(TranscriptRepository).set_action_status(
                user_id, task_id, action_id, "failed" if code else "applied"
            )
        if code:
            logger.warning("action_failed", agent=agent, code=code)
            return Resolution("failed", failure(self._tr, locale, code), code)
        logger.info("action_applied", agent=agent)
        return Resolution("applied", self._tr.t("actions.applied", locale))
