from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from calendar_agent.application.ports import CalendarUnavailable, InvalidGrant
from calendar_agent.application.tokens import SERVICE, NotConnected, TokenProvider
from calendar_agent.testing import FakeGoogleOAuth
from shared.ports.credentials import CredentialStore
from shared.testing.fakes import FixedClock, InMemoryCredentialStore, InMemoryUnitOfWorkFactory

NOW = datetime(2026, 10, 14, 6, 30, tzinfo=UTC)


def provider(expires: datetime):
    store = InMemoryCredentialStore()
    uow = InMemoryUnitOfWorkFactory({CredentialStore: store})
    oauth = FakeGoogleOAuth()
    user = uuid4()
    store.rows[(user, SERVICE)] = {
        "access_token": "access-1",
        "refresh_token": "refresh-1",
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
    }
    return TokenProvider(uow=uow, oauth=oauth, clock=FixedClock(NOW)), store, oauth, user


async def test_valid_token_is_reused() -> None:
    tokens, _, oauth, user = provider(NOW + timedelta(minutes=30))
    assert await tokens.fresh(user) == "access-1"
    assert oauth.refreshed == 0


async def test_expiring_token_is_refreshed_and_the_refresh_token_kept() -> None:
    tokens, store, _oauth, user = provider(NOW + timedelta(seconds=30))
    assert await tokens.fresh(user) == "access-2"
    assert store.rows[(user, SERVICE)]["refresh_token"] == "refresh-1"
    assert store.rows[(user, SERVICE)]["expires_at"] == "2026-10-14T07:30:00Z"


async def test_invalid_grant_deletes_the_connection() -> None:
    tokens, store, oauth, user = provider(NOW)
    oauth.refresh_error = InvalidGrant()
    with pytest.raises(NotConnected):
        await tokens.fresh(user)
    assert (user, SERVICE) not in store.rows


async def test_network_trouble_keeps_the_connection() -> None:
    tokens, store, oauth, user = provider(NOW)
    oauth.refresh_error = CalendarUnavailable()
    with pytest.raises(CalendarUnavailable):
        await tokens.fresh(user)
    assert (user, SERVICE) in store.rows


async def test_not_connected() -> None:
    tokens, _store, _, _ = provider(NOW)
    with pytest.raises(NotConnected):
        await tokens.fresh(uuid4())


@pytest.mark.parametrize("invalid_grant", [False, True])
@pytest.mark.parametrize("reconnect", [False, True])
async def test_refresh_cannot_change_a_newer_connection(invalid_grant, reconnect) -> None:
    import asyncio

    class PausedOAuth(FakeGoogleOAuth):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()
            self.resume = asyncio.Event()

        async def refresh(self, refresh_token):
            self.started.set()
            await self.resume.wait()
            return await super().refresh(refresh_token)

    store = InMemoryCredentialStore()
    user = uuid4()
    await store.put(
        user,
        SERVICE,
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": NOW.isoformat(),
        },
    )
    oauth = PausedOAuth()
    if invalid_grant:
        oauth.refresh_error = InvalidGrant()
    tokens = TokenProvider(
        uow=InMemoryUnitOfWorkFactory({CredentialStore: store}),
        oauth=oauth,
        clock=FixedClock(NOW),
    )
    current = {
        "access_token": "new-access",
        "refresh_token": "new-refresh",
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    pending = asyncio.create_task(tokens.fresh(user))
    try:
        await asyncio.wait_for(oauth.started.wait(), timeout=1)
        if reconnect:
            await store.put(user, SERVICE, current)
        else:
            await store.delete(user, SERVICE)
        oauth.resume.set()
        if reconnect:
            assert await asyncio.wait_for(pending, timeout=1) == "new-access"
            assert await store.get(user, SERVICE) == current
        else:
            with pytest.raises(NotConnected):
                await asyncio.wait_for(pending, timeout=1)
            assert await store.get(user, SERVICE) is None
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
