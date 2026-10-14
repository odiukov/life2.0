"""Sync one user's Garmin and/or Yazio data into health_logs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from shared.observability.logging import get_logger
from shared.ports.clock import Clock
from shared.ports.credentials import CredentialStore, CredentialsUnreadable
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettings, UserSettingsRepository

from sync.application.ports import (
    SERVICES,
    TOKEN_KEYS,
    Credentials,
    ErrorCode,
    GarminClient,
    IntegrationError,
    Service,
    SyncStateRepository,
    YazioClient,
)
from sync.domain.garmin import map_garmin
from sync.domain.rows import Row
from sync.domain.yazio import map_yazio

logger = get_logger(__name__)

Status = Literal[
    "ok",
    "partial",
    "already_fresh",
    "not_connected",
    "disabled",
    "auth_failed",
    "rate_limited",
    "unavailable",
]


@dataclass(frozen=True, slots=True)
class ServiceResult:
    service: Service
    status: Status
    written: int = 0
    unchanged: int = 0


@dataclass(frozen=True, slots=True)
class Preview:
    status: Status
    counts: dict[str, int]
    failures: tuple[str, ...]


def to_health_log(row: Row) -> HealthLogRow:
    return HealthLogRow(
        type=row.type,
        recorded_at=row.recorded_at,
        data=dict(row.data),
        source=row.source,
        agent=row.agent,
    )


@dataclass(frozen=True, slots=True)
class _Fetched:
    rows: list[Row]
    failures: tuple[str, ...]
    token: Any  # str for Garmin, dict for Yazio, None to keep the stored one


class SyncUser:
    def __init__(
        self,
        *,
        uow: UnitOfWorkFactory,
        garmin: GarminClient | None,
        yazio: YazioClient | None,
        clock: Clock,
        cooldown: timedelta,
        garmin_days: int = 7,
        yazio_days: int = 2,
    ) -> None:
        self._uow = uow
        self._garmin = garmin
        self._yazio = yazio
        self._clock = clock
        self._cooldown = cooldown
        self._days: Mapping[Service, int] = {"garmin": garmin_days, "yazio": yazio_days}

    async def __call__(
        self, user_id: UUID, services: Sequence[Service] = SERVICES
    ) -> list[ServiceResult]:
        return [await self._one(user_id, service) for service in dict.fromkeys(services)]

    def _enabled(self, service: Service) -> bool:
        return (self._garmin if service == "garmin" else self._yazio) is not None

    async def preview(self, user_id: UUID, service: Service) -> Preview:
        """Fetch and map without writing rows, tokens, or sync state."""
        if not self._enabled(service):
            return Preview("disabled", {}, ())
        try:
            async with self._uow.for_user(user_id) as tx:
                settings = await tx.repo(UserSettingsRepository).get(user_id)
                payload = await tx.repo(CredentialStore).get(user_id, service)
        except CredentialsUnreadable:
            return Preview("auth_failed", {}, ())
        if payload is None:
            return Preview("not_connected", {}, ())
        credentials = Credentials.from_payload(payload)
        if credentials is None:
            return Preview("auth_failed", {}, ())
        try:
            fetched = await self._fetch(
                service,
                self._window(settings, self._clock.now(), service),
                credentials,
                payload.get(TOKEN_KEYS[service]),
                settings,
            )
        except IntegrationError as error:
            return Preview(error.code, {}, ())
        counts: dict[str, int] = {}
        for row in fetched.rows:
            counts[row.type] = counts.get(row.type, 0) + 1
        return Preview("partial" if fetched.failures else "ok", counts, fetched.failures)

    async def _one(self, user_id: UUID, service: Service) -> ServiceResult:
        if not self._enabled(service):
            return ServiceResult(service, "disabled")
        now = self._clock.now()
        credentials: Credentials | None = None
        try:
            async with self._uow.for_user(user_id) as tx:
                settings = await tx.repo(UserSettingsRepository).get(user_id)
                try:
                    payload = await tx.repo(CredentialStore).get(user_id, service)
                except CredentialsUnreadable:
                    payload = {}
                if payload is None:
                    return ServiceResult(service, "not_connected")
                revision = (
                    await tx.repo(CredentialStore).revision(user_id, service) if payload else None
                )
                credentials = Credentials.from_payload(payload)
                if not await tx.repo(SyncStateRepository).claim(
                    user_id, service, now=now, cooldown=self._cooldown
                ):
                    return ServiceResult(service, "already_fresh")
        except Exception:
            return await self._fail(user_id, service, "unavailable")
        if credentials is None:
            return await self._fail(user_id, service, "auth_failed")

        stored = payload.get(TOKEN_KEYS[service])
        try:
            fetched = await self._fetch(
                service, self._window(settings, now, service), credentials, stored, settings
            )
        except IntegrationError as error:
            return await self._fail(user_id, service, error.code, revision=revision)
        except Exception:
            return await self._fail(user_id, service, "unavailable", revision=revision)

        if fetched.token is not None and fetched.token != stored:
            try:
                async with self._uow.for_user(user_id) as tx:
                    store = tx.repo(CredentialStore)
                    if await store.revision(user_id, service) != revision:
                        return ServiceResult(service, "unavailable")
                    await store.merge(user_id, service, {TOKEN_KEYS[service]: fetched.token})
                    next_revision = await store.revision(user_id, service)
                revision = next_revision
            except Exception:  # keep going: the rows are still worth writing
                logger.warning(
                    "sync_token_not_saved",
                    code="unavailable",
                    service=service,
                    user_id=str(user_id),
                )

        try:
            async with self._uow.for_user(user_id) as tx:
                # Hold the credential lock through row writes and success marking.
                # This also covers reconnects between the token and data transactions.
                if await tx.repo(CredentialStore).revision(user_id, service) != revision:
                    return ServiceResult(service, "unavailable")
                logs = tx.repo(HealthLogRepository)
                written = 0
                for row in fetched.rows:
                    written += await logs.upsert(user_id, to_health_log(row))
                await tx.repo(SyncStateRepository).finish(
                    user_id,
                    service,
                    now=self._clock.now(),
                    error="partial" if fetched.failures else None,
                    success=True,
                )
        except Exception:
            return await self._fail(user_id, service, "unavailable", revision=revision)
        status: Status = "partial" if fetched.failures else "ok"
        logger.info("sync_done", service=service, user_id=str(user_id), code=status)
        return ServiceResult(
            service, status, written=written, unchanged=len(fetched.rows) - written
        )

    def _window(self, settings: UserSettings, now: datetime, service: Service) -> list[date]:
        today = settings.today(now)
        return [today - timedelta(days=offset) for offset in range(self._days[service])]

    async def _fetch(
        self,
        service: Service,
        days: list[date],
        credentials: Credentials,
        stored: object,
        settings: UserSettings,
    ) -> _Fetched:
        if service == "garmin":
            assert self._garmin is not None
            garmin, token = await self._garmin.fetch(
                days, credentials, stored if isinstance(stored, str) else None
            )
            return _Fetched(map_garmin(garmin, settings.timezone), garmin.failures, token)
        assert self._yazio is not None
        yazio, new = await self._yazio.fetch(
            days, credentials, stored if isinstance(stored, Mapping) else None
        )
        return _Fetched(map_yazio(yazio, settings.timezone), yazio.failures, new)

    async def _fail(
        self, user_id: UUID, service: Service, code: ErrorCode, *, revision: str | None = None
    ) -> ServiceResult:
        logger.warning("sync_failed", code=code, service=service, user_id=str(user_id))
        try:
            async with self._uow.for_user(user_id) as tx:
                if (
                    revision is not None
                    and await tx.repo(CredentialStore).revision(user_id, service) != revision
                ):
                    return ServiceResult(service, "unavailable")
                await tx.repo(SyncStateRepository).finish(
                    user_id, service, now=self._clock.now(), error=code, success=False
                )
        except Exception:
            logger.warning(
                "sync_state_not_saved", code="unavailable", service=service, user_id=str(user_id)
            )
        return ServiceResult(service, code)
