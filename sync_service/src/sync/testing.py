"""In-memory backend and scripted clients with the same contracts as the real ones (see tests/contract)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from shared.ports.credentials import CredentialStore, CredentialsUnreadable
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    InMemoryCredentialStore,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

from sync.application.ports import (
    SERVICES,
    Credentials,
    DueUser,
    Service,
    SyncDirectory,
    SyncStateRepository,
    SyncStatus,
)
from sync.domain.garmin import GarminBundle
from sync.domain.yazio import YazioBundle


class InMemorySyncState:
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, str], SyncStatus] = {}

    async def get(self, user_id: UUID, service: Service) -> SyncStatus | None:
        return self.rows.get((user_id, service))

    async def claim(
        self, user_id: UUID, service: Service, *, now: datetime, cooldown: timedelta
    ) -> bool:
        current = self.rows.get((user_id, service), SyncStatus(None, None, None))
        if current.last_attempt_at is not None and current.last_attempt_at > now - cooldown:
            return False
        self.rows[(user_id, service)] = replace(current, last_attempt_at=now)
        return True

    async def finish(
        self, user_id: UUID, service: Service, *, now: datetime, error: str | None, success: bool
    ) -> None:
        current = self.rows.get((user_id, service), SyncStatus(None, None, None))
        self.rows[(user_id, service)] = SyncStatus(
            now, now if success else current.last_success_at, error
        )


class RecordingCredentialStore(InMemoryCredentialStore):
    """Adds what the use-case tests need: unreadable rows and a record of merges."""

    def __init__(self) -> None:
        super().__init__()
        self.plaintext: set[tuple[UUID, str]] = set()
        self.unreadable: set[tuple[UUID, str]] = set()
        self.merges: list[tuple[UUID, str, dict[str, Any]]] = []

    def for_tenant(self, user_id: UUID | None) -> RecordingCredentialStore:
        store = RecordingCredentialStore()
        store._tenant = user_id
        store.rows = self.rows
        store.plaintext = self.plaintext
        store.unreadable = self.unreadable
        store.merges = self.merges
        return store

    async def get(self, user_id: UUID, service: str) -> dict[str, Any] | None:
        if self._tenant is not None and self._tenant != user_id:
            return None
        if (user_id, service) in self.unreadable:
            raise CredentialsUnreadable(service)
        result = await super().get(user_id, service)
        self.plaintext.discard((user_id, service))
        return result

    async def merge(self, user_id: UUID, service: str, changes: Mapping[str, Any]) -> None:
        self.merges.append((user_id, service, dict(changes)))
        await super().merge(user_id, service, changes)


class FailingHealthLogs(InMemoryHealthLogs):
    fail_upserts = False

    async def upsert(self, user_id: UUID, row: HealthLogRow) -> bool:
        if self.fail_upserts:
            raise RuntimeError("database is down")
        return await super().upsert(user_id, row)


class InMemorySyncDirectory:
    """The rule of integration_users_due(), in Python; tests/contract keeps the two in step."""

    def __init__(self, backend: MemoryBackend) -> None:
        self._backend = backend

    async def due(self, now: datetime, hour: int) -> list[DueUser]:
        found: dict[UUID, list[Service]] = {}
        for user_id, service in sorted(
            self._backend.credentials.rows, key=lambda k: (str(k[0]), k[1])
        ):
            if service not in SERVICES or user_id not in self._backend.users.rows:
                continue
            zone = (await self._backend.users.get(user_id)).timezone
            local = now.astimezone(zone)
            status = self._backend.state.rows.get((user_id, service), SyncStatus(None, None, None))
            if local.hour < hour:
                continue
            if (
                status.last_success_at is not None
                and status.last_success_at.astimezone(zone).date() >= local.date()
            ):
                continue
            if status.last_attempt_at is not None and status.last_attempt_at > now - timedelta(
                hours=1
            ):
                continue
            # SQL NOT(auth_failed AND local_attempt_date = today) also excludes NULL attempts.
            if status.last_error == "auth_failed" and (
                status.last_attempt_at is None
                or status.last_attempt_at.astimezone(zone).date() == local.date()
            ):
                continue
            found.setdefault(user_id, []).append(service)
        return [
            DueUser(user, tuple(s for s in SERVICES if s in services))
            for user, services in found.items()
        ]

    async def plaintext(self) -> list[tuple[UUID, str]]:
        return sorted(self._backend.credentials.plaintext, key=lambda k: (str(k[0]), k[1]))


@dataclass
class MemoryBackend:
    users: InMemoryUserSettings = field(default_factory=InMemoryUserSettings)
    credentials: RecordingCredentialStore = field(default_factory=RecordingCredentialStore)
    logs: FailingHealthLogs = field(default_factory=FailingHealthLogs)
    state: InMemorySyncState = field(default_factory=InMemorySyncState)
    directory: InMemorySyncDirectory = field(init=False)
    uow: InMemoryUnitOfWorkFactory = field(init=False)

    def __post_init__(self) -> None:
        self.directory = InMemorySyncDirectory(self)
        self.uow = InMemoryUnitOfWorkFactory(
            {
                UserSettingsRepository: self.users,
                CredentialStore: self.credentials,
                HealthLogRepository: self.logs,
                SyncStateRepository: self.state,
                SyncDirectory: self.directory,
            }
        )


class FakeGarminClient:
    def __init__(
        self,
        bundle: GarminBundle | None = None,
        *,
        token: str | None = None,
        error: Exception | None = None,
        check_error: Exception | None = None,
    ) -> None:
        self.bundle, self.token, self.error, self.check_error = (
            bundle or GarminBundle(),
            token,
            error,
            check_error,
        )
        self.calls: list[tuple[list[date], Credentials, str | None]] = []
        self.checks: list[Credentials] = []

    async def fetch(
        self, days: Sequence[date], credentials: Credentials, token: str | None
    ) -> tuple[GarminBundle, str | None]:
        if self.error is not None:
            raise self.error
        self.calls.append((list(days), credentials, token))
        return self.bundle, self.token

    async def check(self, credentials: Credentials) -> None:
        self.checks.append(credentials)
        if self.check_error is not None:
            raise self.check_error


class FakeYazioClient:
    def __init__(
        self,
        bundle: YazioBundle | None = None,
        *,
        token: dict[str, Any] | None = None,
        error: Exception | None = None,
        check_error: Exception | None = None,
    ) -> None:
        self.bundle, self.token, self.error, self.check_error = (
            bundle or YazioBundle(),
            token,
            error,
            check_error,
        )
        self.calls: list[tuple[list[date], Credentials, Mapping[str, Any] | None]] = []
        self.checks: list[Credentials] = []

    async def fetch(
        self, days: Sequence[date], credentials: Credentials, token: Mapping[str, Any] | None
    ) -> tuple[YazioBundle, dict[str, Any] | None]:
        if self.error is not None:
            raise self.error
        self.calls.append((list(days), credentials, token))
        return self.bundle, self.token

    async def check(self, credentials: Credentials) -> None:
        self.checks.append(credentials)
        if self.check_error is not None:
            raise self.check_error
