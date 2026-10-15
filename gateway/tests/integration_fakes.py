from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from gateway.integrations import STATE_TTL
from shared.ports.clock import Clock


@dataclass
class InMemoryOAuthStates:
    clock: Clock
    rows: dict[UUID, dict[str, object]] = field(default_factory=dict)

    async def create(self, user_id: UUID, nonce: UUID, verifier: str) -> None:
        self.rows[nonce] = {
            "user": user_id,
            "verifier": verifier,
            "created": self.clock.now(),
            "used": False,
        }

    async def claim(self, user_id: UUID, nonce: UUID, *, now: datetime) -> str | None:
        row = self.rows.get(nonce)
        if not row or row["user"] != user_id or row["used"] or row["created"] <= now - STATE_TTL:  # type: ignore[operator]
            return None
        row["used"] = True
        return str(row["verifier"])


@dataclass
class InMemorySourceActivity:
    rows: list[tuple[UUID, str, datetime]] = field(default_factory=list)

    async def summary(
        self, user_id: UUID, sources: list[str], since: datetime
    ) -> tuple[int, datetime | None]:
        found = [
            at for uid, src, at in self.rows if uid == user_id and src in sources and at >= since
        ]
        return len(found), max(found) if found else None
