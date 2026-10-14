"""Fetch and count one user's sync rows, or run a real sync.

    make sync-smoke USER_ID=<uuid> DRY_RUN=1
    make sync-smoke USER_ID=<uuid>

Output includes statuses and counts only.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from uuid import UUID

from pydantic import ValidationError
from pydantic_settings import SettingsError
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.adapters.secrets import AesGcmSecretBox
from shared.observability.logging import configure_logging

from sync.adapters.db import sync_uow
from sync.adapters.garmin_client import GarminConnectClient
from sync.adapters.yazio_client import YazioHttpClient
from sync.application.ports import SERVICES, Service
from sync.application.sync_user import Preview, ServiceResult, SyncUser
from sync.settings import SyncServiceSettings

GOOD = {"ok", "partial", "not_connected", "disabled"}


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m sync.smoke")
    parser.add_argument("--user", type=UUID, required=True)
    parser.add_argument("--service", choices=SERVICES, action="append")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _format_preview(service: Service, preview: Preview) -> str:
    counts = ", ".join(f"{kind}={n}" for kind, n in sorted(preview.counts.items())) or "no rows"
    return f"{service}: {preview.status} ({counts}); failed parts={len(preview.failures)}"


def _format_result(result: ServiceResult) -> str:
    return (
        f"{result.service}: {result.status} "
        f"(written={result.written}, unchanged={result.unchanged})"
    )


async def _run(
    settings: SyncServiceSettings, user: UUID, services: list[Service], dry_run: bool
) -> int:
    engine = create_engine(settings.database)
    options, clock = settings.sync, SystemClock()
    yazio = (
        YazioHttpClient(
            options.yazio_client_id.get_secret_value(),
            options.yazio_client_secret.get_secret_value(),
            clock=clock,
        )
        if options.yazio_client_id and options.yazio_client_secret
        else None
    )
    sync = SyncUser(
        uow=sync_uow(engine, AesGcmSecretBox.from_settings(settings.secrets)),
        garmin=GarminConnectClient(),
        yazio=yazio,
        clock=clock,
        cooldown=timedelta(0),
        garmin_days=options.garmin_days,
        yazio_days=options.yazio_days,
    )
    ok = True
    try:
        for service in services:
            try:
                if dry_run:
                    preview = await sync.preview(user, service)
                    print(_format_preview(service, preview))
                    ok &= preview.status in GOOD
                else:
                    [result] = await sync(user, [service])
                    print(_format_result(result))
                    ok &= result.status in GOOD
            except Exception:
                print(f"{service}: unavailable (no rows)")
                ok = False
    finally:
        await engine.dispose()
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> None:
    args = _parse(sys.argv[1:] if argv is None else argv)
    try:
        settings = SyncServiceSettings()
    except (ValidationError, SettingsError):
        raise SystemExit("sync_configuration_invalid") from None
    configure_logging(settings.telemetry, private_debug=True)
    services: list[Service] = list(dict.fromkeys(args.service)) if args.service else list(SERVICES)
    try:
        code = asyncio.run(_run(settings, args.user, services, args.dry_run))
    except Exception:
        raise SystemExit("sync_smoke_unavailable") from None
    sys.exit(code)


if __name__ == "__main__":
    main()
