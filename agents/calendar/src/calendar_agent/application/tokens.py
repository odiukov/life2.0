"""A fresh Google access token per user; refreshes lazily and never drops a connection by accident."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from shared.ports.clock import Clock
from shared.ports.credentials import CredentialStore, CredentialsUnreadable
from shared.ports.uow import UnitOfWorkFactory

from calendar_agent.application.ports import GoogleOAuth, InvalidGrant, Tokens

SERVICE = "google_calendar"
SKEW = timedelta(seconds=60)


class NotConnected(Exception):
    pass


def expires_at(clock: Clock, tokens: Tokens) -> str:
    return (clock.now() + timedelta(seconds=tokens.expires_in)).isoformat().replace("+00:00", "Z")


class TokenProvider:
    def __init__(self, *, uow: UnitOfWorkFactory, oauth: GoogleOAuth, clock: Clock) -> None:
        self._uow = uow
        self._oauth = oauth
        self._clock = clock

    async def fresh(self, user_id: UUID) -> str:
        # A refresh result belongs only to the credential generation that started it.
        while True:
            async with self._uow.for_user(user_id) as tx:
                try:
                    store = tx.repo(CredentialStore)
                    creds = await store.get(user_id, SERVICE)
                    revision = await store.revision(user_id, SERVICE)
                except CredentialsUnreadable:
                    raise NotConnected from None
            if not creds or not creds.get("access_token"):
                raise NotConnected
            try:
                expiry = datetime.fromisoformat(
                    str(creds.get("expires_at", "")).replace("Z", "+00:00")
                )
            except ValueError:
                expiry = self._clock.now()
            if expiry > self._clock.now() + SKEW:
                return str(creds["access_token"])
            refresh = creds.get("refresh_token")
            if not refresh:
                raise NotConnected
            try:
                tokens = await self._oauth.refresh(str(refresh))  # CalendarUnavailable propagates
            except InvalidGrant:
                async with self._uow.for_user(user_id) as tx:
                    store = tx.repo(CredentialStore)
                    if await store.revision(user_id, SERVICE) != revision:
                        continue
                    await store.delete(user_id, SERVICE)
                raise NotConnected from None
            changes = {
                "access_token": tokens.access_token,
                "expires_at": expires_at(self._clock, tokens),
            }
            if tokens.refresh_token:
                changes["refresh_token"] = tokens.refresh_token  # Google may rotate it
            async with self._uow.for_user(user_id) as tx:
                store = tx.repo(CredentialStore)
                if await store.revision(user_id, SERVICE) != revision:
                    continue
                await store.merge(user_id, SERVICE, changes)
            return tokens.access_token
