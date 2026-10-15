"""Home skills. home.ask runs the household's model+tools; everything else is structured."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from urllib.parse import urlparse
from uuid import UUID

from shared.a2a.executor import SkillHandler, SkillResult
from shared.a2a.proposals import Proposal, to_data
from shared.a2a.request import SkillRequest
from shared.observability.logging import get_logger
from shared.ports.clock import Clock
from shared.ports.credentials import CredentialsUnreadable
from shared.ports.household_credentials import (
    HouseholdConnection,
    HouseholdCredentialStore,
    NoHousehold,
)
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Home

from home.application.ports import (
    SERVICE,
    HomeAgent,
    HomeAssistant,
    HomeUnavailable,
    InvalidToken,
    ToolRejected,
)
from home.domain.actions import action_key, is_read_only, target

logger = get_logger(__name__)
Body = Callable[[SkillRequest], Awaitable[SkillResult]]


def _fail(code: str) -> SkillResult:
    return SkillResult(output=code, failed=True)


def _valid_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value.strip())
        _ = parsed.port  # Validate malformed port values as well as the hostname.
    except ValueError:
        return None
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(ch.isspace() for ch in value.strip())
    ):
        return None
    return value.strip().rstrip("/")


def build_skills(
    *,
    uow: UnitOfWorkFactory,
    assistant: HomeAssistant,
    agent: HomeAgent,
    clock: Clock,
    translator: Translator,
    default_locale: str,
    ask_timeout_s: float,
) -> dict[str, SkillHandler]:
    async def connection(user: UUID) -> tuple[HouseholdConnection | None, str]:
        async with uow.for_user(user) as tx:
            settings = await tx.repo(UserSettingsRepository).get(user)
            try:
                conn = await tx.repo(HouseholdCredentialStore).get(SERVICE)
            except CredentialsUnreadable:
                conn = None
        return conn, settings.locale or default_locale

    async def connect(request: SkillRequest) -> SkillResult:
        base_url, token = _valid_url(request.params.get("base_url")), request.params.get("token")
        if base_url is None or not isinstance(token, str) or not token.strip():
            return _fail("invalid_params")
        try:
            await assistant.ping(base_url, token)
        except InvalidToken:
            return _fail("invalid_token")
        except HomeUnavailable:
            return _fail("home_unavailable")
        try:
            async with uow.for_user(request.user_id) as tx:
                stored = await tx.repo(HouseholdCredentialStore).put(
                    SERVICE, {"base_url": base_url, "token": token}, actor=request.user_id
                )
        except NoHousehold:
            return _fail("no_household")
        logger.info("home_connected", version=stored.version)
        return SkillResult(
            output="connected", data={"status": "connected", "version": stored.version}
        )

    async def disconnect(request: SkillRequest) -> SkillResult:
        async with uow.for_user(request.user_id) as tx:
            await tx.repo(HouseholdCredentialStore).delete(SERVICE)
        return SkillResult(output="disconnected", data={"status": "disconnected"})

    async def status(request: SkillRequest) -> SkillResult:
        conn, _ = await connection(request.user_id)
        data: dict[str, object] = {
            "connected": conn is not None,
            "connected_by": conn.updated_by_name if conn else None,
            "connected_at": conn.updated_at.isoformat() if conn else None,
        }
        return SkillResult(output=str(conn is not None).lower(), data=data)

    async def test(request: SkillRequest) -> SkillResult:
        conn, _ = await connection(request.user_id)
        if conn is None:
            return _fail("not_connected")
        try:
            version = await assistant.ping(
                str(conn.payload["base_url"]), str(conn.payload["token"])
            )
        except InvalidToken:
            return _fail("invalid_token")
        except HomeUnavailable:
            return _fail("home_unavailable")
        return SkillResult(output="ok", data={"status": "ok", "ha_version": version})

    async def ask(request: SkillRequest) -> SkillResult:
        conn, locale = await connection(request.user_id)
        if conn is None:
            return _fail("not_connected")
        try:
            async with asyncio.timeout(ask_timeout_s):
                outcome = await agent.run(request.text, conn, locale)
        except (TimeoutError, HomeUnavailable):
            logger.warning("home_ask_unavailable")
            return _fail("home_unavailable")
        if outcome.proposal is None:
            return SkillResult(output=outcome.text)
        call = outcome.proposal
        summary = translator.t(
            action_key(call.tool), locale, tool=call.tool, target=target(call.args)
        )
        payload = {
            "tool": call.tool,
            "args": dict(call.args),
            "household_id": str(conn.household_id),
            "credentials_version": conn.version,
        }
        return SkillResult(
            output=outcome.text, data=to_data(Proposal("home.call_tool", summary, payload))
        )

    async def apply(request: SkillRequest) -> SkillResult:
        payload = request.params.get("payload")
        if not isinstance(payload, Mapping):
            return _fail("invalid_params")
        tool, args = payload.get("tool"), payload.get("args")
        house, version = payload.get("household_id"), payload.get("credentials_version")
        if (
            not isinstance(tool, str)
            or is_read_only(tool)
            or not isinstance(args, Mapping)
            or not isinstance(house, str)
            or type(version) is not int
            or version < 1
        ):
            return _fail("invalid_params")
        async with uow.for_user(request.user_id) as tx:
            store = tx.repo(HouseholdCredentialStore)
            current = await store.household_id()
            try:
                conn = await store.get(SERVICE) if current is not None else None
            except CredentialsUnreadable:
                conn = None
        if current is None or str(current) != house:
            return _fail("household_changed")  # the proposal belongs to a household the user left
        if conn is None:
            return _fail("not_connected")
        if conn.version != version:
            return _fail("connection_changed")
        try:
            await assistant.call_tool(conn, tool, args)
        except HomeUnavailable:
            return _fail("home_unavailable")
        except ToolRejected:
            return _fail("rejected_by_home")
        logger.info("home_action_applied", tool=tool)
        return SkillResult(output="applied", data={"status": "applied"})

    return {
        Home.CONNECT: _wrap(connect),
        Home.DISCONNECT: _wrap(disconnect),
        Home.STATUS: _wrap(status),
        Home.TEST: _wrap(test),
        Home.ASK: _wrap(ask),
        Home.APPLY: _wrap(apply),
    }


def _wrap(body: Body) -> SkillHandler:
    async def run(request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        return await body(request)

    return run
