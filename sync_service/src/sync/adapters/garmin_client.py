"""Garmin Connect through the unofficial `garminconnect` library (blocking; run in a worker thread)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import date
from functools import partial
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

from sync.application.ports import AuthFailed, Credentials, RateLimited, Unavailable
from sync.domain.garmin import GarminBundle, Payload


class _Stop(Exception):
    """Garmin asked us to slow down: make no further calls in this run."""


class GarminConnectClient:
    def __init__(self, factory: Callable[[str, str], Any] = Garmin) -> None:
        self._factory = factory

    async def fetch(
        self, days: Sequence[date], credentials: Credentials, token: str | None
    ) -> tuple[GarminBundle, str | None]:
        return await asyncio.to_thread(self._fetch, list(days), credentials, token)

    async def check(self, credentials: Credentials) -> None:
        await asyncio.to_thread(self._login, credentials, None, fresh=True)

    def _login(self, credentials: Credentials, token: str | None, *, fresh: bool = False) -> Any:
        # A non-JSON tokenstore is read as a file path by garminconnect; only inline JSON is passed on.
        tokenstore = token if token and token.lstrip().startswith("{") else None
        try:
            api = self._factory(credentials.email, credentials.password)
            if fresh or tokenstore is None:
                # Garmin.login(None) consults GARMINTOKENS and can skip credentials.
                # The underlying client authenticates directly, without token-store IO.
                needs_mfa, _ = api.client.login(
                    credentials.email, credentials.password, return_on_mfa=True
                )
                if not fresh and not needs_mfa:
                    api._load_profile_and_settings()
            else:
                needs_mfa, _ = api.login(tokenstore=tokenstore)
        except GarminConnectAuthenticationError:
            raise AuthFailed from None
        except GarminConnectTooManyRequestsError:
            raise RateLimited from None
        except Exception:
            raise Unavailable from None
        if needs_mfa:
            raise AuthFailed from None  # an MFA prompt cannot be answered by a scheduled job
        return api

    def _fetch(
        self, days: list[date], credentials: Credentials, token: str | None
    ) -> tuple[GarminBundle, str | None]:
        api = self._login(credentials, token)
        failures: list[str] = []
        sleep: list[tuple[date, Payload]] = []
        stats: list[tuple[date, Payload]] = []
        hrv: list[tuple[date, Payload]] = []
        activities: list[Payload] = []

        def part(label: str, call: Callable[[], Any]) -> Any:
            try:
                return call()
            except GarminConnectTooManyRequestsError:
                raise _Stop from None
            except GarminConnectNotFoundError:
                return None  # e.g. no HRV on this device: no data, not a failure
            except Exception:  # auth, connection, parsing: name the part, keep no text
                failures.append(label)
                return None

        try:
            for day in days:
                if (
                    raw := part(f"sleep {day}", partial(api.get_sleep_data, day.isoformat()))
                ) is not None:
                    sleep.append((day, raw))
            if days:
                found = part(
                    "activities",
                    lambda: api.get_activities_by_date(
                        min(days).isoformat(), max(days).isoformat()
                    ),
                )
                if found is not None and not isinstance(found, list | tuple):
                    failures.append("activities")
                else:
                    activities = [a for a in found or [] if isinstance(a, dict)]
            for day in days:
                if (
                    raw := part(f"stats {day}", partial(api.get_stats, day.isoformat()))
                ) is not None:
                    stats.append((day, raw))
            for day in days:
                if (
                    raw := part(f"hrv {day}", partial(api.get_hrv_data, day.isoformat()))
                ) is not None:
                    hrv.append((day, raw))
        except _Stop:
            failures.append("rate_limited")
        try:
            new_token: str | None = api.client.dumps()
        except Exception:
            new_token = None
        bundle = GarminBundle(
            tuple(sleep), tuple(activities), tuple(stats), tuple(hrv), tuple(failures)
        )
        return bundle, new_token
