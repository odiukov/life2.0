from __future__ import annotations

from dataclasses import dataclass

from shared.ports.credentials import CredentialStore, CredentialsUnreadable
from shared.ports.uow import UnitOfWorkFactory

from sync.application.ports import SyncDirectory


@dataclass(frozen=True, slots=True)
class ResealReport:
    resealed: int
    remaining: int


async def reseal_plaintext(uow: UnitOfWorkFactory) -> ResealReport:
    """Reading a plaintext row through CredentialStore re-seals it; do that for every such row."""
    async with uow.system() as tx:
        rows = await tx.repo(SyncDirectory).plaintext()
    resealed = 0
    for user_id, service in rows:
        try:
            async with uow.for_user(user_id) as tx:
                await tx.repo(CredentialStore).get(user_id, service)
            resealed += 1
        except CredentialsUnreadable:
            continue  # cannot happen for plaintext; counted in `remaining`
    async with uow.system() as tx:
        remaining = len(await tx.repo(SyncDirectory).plaintext())
    return ResealReport(resealed, remaining)
