"""Seal every integration credential still stored as plaintext. Run once after deploying 3b.

docker compose run --rm sync-service python -m sync.reencrypt
"""

from __future__ import annotations

import asyncio
import sys

from shared.adapters.db.engine import create_engine
from shared.adapters.secrets import AesGcmSecretBox
from shared.observability.logging import configure_logging

from sync.adapters.db import sync_uow
from sync.application.reseal import reseal_plaintext
from sync.settings import SyncServiceSettings


async def _run(settings: SyncServiceSettings) -> int:
    engine = create_engine(settings.database)
    try:
        report = await reseal_plaintext(
            sync_uow(engine, AesGcmSecretBox.from_settings(settings.secrets))
        )
    finally:
        await engine.dispose()
    print(f"resealed {report.resealed} credential rows; {report.remaining} plaintext rows remain")
    return 0 if report.remaining == 0 else 1


def main() -> None:
    settings = SyncServiceSettings()
    configure_logging(settings.telemetry)
    sys.exit(asyncio.run(_run(settings)))


if __name__ == "__main__":
    main()
