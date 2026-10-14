"""Run the daily digest once for operations or acceptance testing."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from shared.adapters.clock import SystemClock
from shared.testing.fakes import FakeScheduler, FixedClock

from kitchen.composition import build_runtime
from kitchen.settings import KitchenSettings


async def _main(now: str | None) -> None:
    clock = FixedClock(datetime.fromisoformat(now)) if now else SystemClock()
    runtime = build_runtime(KitchenSettings(), clock=clock, scheduler=FakeScheduler())
    try:
        sent = await runtime.digest_job()
        print(f"digests sent: {sent}")
    finally:
        await runtime.http.aclose()
        await runtime.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", help="ISO 8601 instant for a one-shot test run")
    asyncio.run(_main(parser.parse_args().now))


if __name__ == "__main__":
    main()
