"""Sign-in persistence. SQL goes through the c0009 functions only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, TypedDict
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True, slots=True)
class Profile:
    user_id: UUID
    name: str
    email: str | None


@dataclass(frozen=True, slots=True)
class Flow:
    verifier: str
    nonce: str
    challenge: str


@dataclass(frozen=True, slots=True)
class Rotation:
    status: Literal["ok", "expired", "reused"]
    profile: Profile | None


class AuthStore(Protocol):
    async def begin_flow(
        self,
        state_hash: str,
        provider: str,
        verifier: str,
        nonce: str,
        challenge: str,
        ttl: timedelta,
    ) -> None: ...
    async def take_flow(self, state_hash: str, provider: str) -> Flow | None: ...
    async def link_identity(
        self, provider: str, subject: str, email: str | None, name: str | None
    ) -> UUID: ...
    async def issue_ticket(
        self, ticket_hash: str, user_id: UUID, challenge: str, ttl: timedelta
    ) -> None: ...
    async def exchange_ticket(
        self,
        ticket_hash: str,
        challenge_hash: str,
        session_id: UUID,
        refresh_hash: str,
        ttl: timedelta,
    ) -> Profile | None: ...
    async def rotate(
        self, session_id: UUID, presented_hash: str, new_hash: str, ttl: timedelta
    ) -> Rotation: ...
    async def revoke(self, session_id: UUID) -> None: ...
    async def active(self, session_id: UUID, user_id: UUID) -> bool: ...


def _secs(ttl: timedelta) -> int:
    return int(ttl.total_seconds())


class SqlAuthStore:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def begin_flow(
        self,
        state_hash: str,
        provider: str,
        verifier: str,
        nonce: str,
        challenge: str,
        ttl: timedelta,
    ) -> None:
        await self._conn.execute(
            text("SELECT auth_begin_flow(:s, :p, :v, :n, :c, :t)"),
            {
                "s": state_hash,
                "p": provider,
                "v": verifier,
                "n": nonce,
                "c": challenge,
                "t": _secs(ttl),
            },
        )

    async def take_flow(self, state_hash: str, provider: str) -> Flow | None:
        row = (
            await self._conn.execute(
                text("SELECT * FROM auth_take_flow(:s, :p)"), {"s": state_hash, "p": provider}
            )
        ).one_or_none()
        return Flow(row.out_verifier, row.out_nonce, row.out_challenge) if row else None

    async def link_identity(
        self, provider: str, subject: str, email: str | None, name: str | None
    ) -> UUID:
        value = (
            await self._conn.execute(
                text("SELECT auth_link_identity(:p, :s, :e, :n)"),
                {"p": provider, "s": subject, "e": email, "n": name},
            )
        ).scalar_one()
        return UUID(str(value))

    async def issue_ticket(
        self, ticket_hash: str, user_id: UUID, challenge: str, ttl: timedelta
    ) -> None:
        await self._conn.execute(
            text("SELECT auth_issue_ticket(:t, :u, :c, :s)"),
            {"t": ticket_hash, "u": user_id, "c": challenge, "s": _secs(ttl)},
        )

    async def exchange_ticket(
        self,
        ticket_hash: str,
        challenge_hash: str,
        session_id: UUID,
        refresh_hash: str,
        ttl: timedelta,
    ) -> Profile | None:
        row = (
            await self._conn.execute(
                text("SELECT * FROM auth_exchange_ticket(:t, :c, :sid, :r, :s)"),
                {
                    "t": ticket_hash,
                    "c": challenge_hash,
                    "sid": session_id,
                    "r": refresh_hash,
                    "s": _secs(ttl),
                },
            )
        ).one_or_none()
        return Profile(row.out_user, row.out_name, row.out_email) if row else None

    async def rotate(
        self, session_id: UUID, presented_hash: str, new_hash: str, ttl: timedelta
    ) -> Rotation:
        row = (
            await self._conn.execute(
                text("SELECT * FROM auth_rotate_session(:sid, :old, :new, :s)"),
                {"sid": session_id, "old": presented_hash, "new": new_hash, "s": _secs(ttl)},
            )
        ).one()
        profile = (
            Profile(row.out_user, row.out_name, row.out_email) if row.out_status == "ok" else None
        )
        return Rotation(row.out_status, profile)

    async def revoke(self, session_id: UUID) -> None:
        await self._conn.execute(text("SELECT auth_revoke_session(:sid)"), {"sid": session_id})

    async def active(self, session_id: UUID, user_id: UUID) -> bool:
        return bool(
            (
                await self._conn.execute(
                    text("SELECT auth_session_active(:sid, :u)"), {"sid": session_id, "u": user_id}
                )
            ).scalar_one()
        )


class Session(TypedDict):
    user: UUID
    hash: str
    expires: datetime
    revoked: bool


@dataclass
class InMemoryAuthStore:
    """Same contract as the SQL functions; time comes from `now()` so tests can expire things."""

    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    flows: dict[str, tuple[str, Flow, datetime]] = field(default_factory=dict)
    identities: dict[tuple[str, str], UUID] = field(default_factory=dict)
    profiles: dict[UUID, Profile] = field(default_factory=dict)
    tickets: dict[str, tuple[UUID, str, datetime]] = field(default_factory=dict)
    sessions: dict[UUID, Session] = field(default_factory=dict)

    async def begin_flow(
        self,
        state_hash: str,
        provider: str,
        verifier: str,
        nonce: str,
        challenge: str,
        ttl: timedelta,
    ) -> None:
        self.flows[state_hash] = (provider, Flow(verifier, nonce, challenge), self.now + ttl)

    async def take_flow(self, state_hash: str, provider: str) -> Flow | None:
        entry = self.flows.get(state_hash)
        if entry is None or entry[0] != provider or entry[2] <= self.now:
            return None
        del self.flows[state_hash]
        return entry[1]

    async def link_identity(
        self, provider: str, subject: str, email: str | None, name: str | None
    ) -> UUID:
        key = (provider, subject)
        if key not in self.identities:
            uid = uuid4()
            self.identities[key] = uid
            self.profiles[uid] = Profile(uid, name or email or provider.title(), email)
        return self.identities[key]

    async def issue_ticket(
        self, ticket_hash: str, user_id: UUID, challenge: str, ttl: timedelta
    ) -> None:
        self.tickets[ticket_hash] = (user_id, challenge, self.now + ttl)

    async def exchange_ticket(
        self,
        ticket_hash: str,
        challenge_hash: str,
        session_id: UUID,
        refresh_hash: str,
        ttl: timedelta,
    ) -> Profile | None:
        entry = self.tickets.get(ticket_hash)
        if entry is None or entry[1] != challenge_hash or entry[2] <= self.now:
            return None
        del self.tickets[ticket_hash]
        self.sessions[session_id] = {
            "user": entry[0],
            "hash": refresh_hash,
            "expires": self.now + ttl,
            "revoked": False,
        }
        return self.profiles.get(entry[0], Profile(entry[0], "user", None))

    async def rotate(
        self, session_id: UUID, presented_hash: str, new_hash: str, ttl: timedelta
    ) -> Rotation:
        s = self.sessions.get(session_id)
        if s is None or s["revoked"] or s["expires"] <= self.now:
            return Rotation("expired", None)
        if s["hash"] != presented_hash:
            s["revoked"] = True
            return Rotation("reused", None)
        s["hash"] = new_hash
        s["expires"] = self.now + ttl
        user = s["user"]
        return Rotation("ok", self.profiles.get(user, Profile(user, "user", None)))

    async def revoke(self, session_id: UUID) -> None:
        if session_id in self.sessions:
            self.sessions[session_id]["revoked"] = True

    async def active(self, session_id: UUID, user_id: UUID) -> bool:
        s = self.sessions.get(session_id)
        return bool(s and s["user"] == user_id and not s["revoked"] and s["expires"] > self.now)
