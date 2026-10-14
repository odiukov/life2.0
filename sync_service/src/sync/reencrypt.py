"""Seal every integration credential still stored as plaintext. Run once after deploying 3b.

docker compose run --rm sync-service python -m sync.reencrypt
"""

from __future__ import annotations

import asyncio
import sys

from pydantic import ValidationError
from pydantic_settings import SettingsError
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
    try:
        settings = SyncServiceSettings()
    except (ValidationError, SettingsError):
        raise SystemExit("sync_configuration_invalid") from None
    try:
        configure_logging(settings.telemetry, private_debug=True)
        code = asyncio.run(_run(settings))
    except Exception:
        raise SystemExit("sync_reencrypt_unavailable") from None
    sys.exit(code)


if __name__ == "__main__":
    main()
