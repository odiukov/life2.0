"""Yazio's private mobile API (OAuth password/refresh grants, consumed-items diary)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from shared.adapters.clock import SystemClock
from shared.ports.clock import Clock

from sync.application.ports import AuthFailed, Credentials, RateLimited, Unavailable
from sync.domain.yazio import (
    YazioBundle,
    YazioItem,
    item_from_product,
    item_from_recipe,
    item_from_simple,
)

BASE_URL = "https://yzapi.yazio.com/v18"
USER_AGENT = "YAZIO/12.31.0 (com.yazio.android; build:411052340; Android 34) Ktor"
EXPIRY_MARGIN = timedelta(minutes=5)


class _Stop(Exception):
    """Yazio answered 429: make no further calls in this run."""


def _raise_for_login(response: httpx.Response) -> dict[str, Any]:
    if response.status_code in (400, 401, 403):
        raise AuthFailed from None
    if response.status_code == 429:
        raise RateLimited from None
    if response.status_code >= 400:
        raise Unavailable from None
    try:
        body = response.json()
    except ValueError:
        raise Unavailable from None
    if (
        not isinstance(body, dict)
        or not isinstance(body.get("access_token"), str)
        or not body["access_token"]
    ):
        raise Unavailable from None
    return body


class YazioHttpClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        base_url: str = BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._base_url = base_url
        self._transport = transport
        self._clock = clock or SystemClock()

    def _http(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=timeout,
            transport=self._transport,
        )

    def _token(self, grant: Mapping[str, Any]) -> dict[str, Any]:
        expires_in = grant.get("expires_in")
        seconds = expires_in if isinstance(expires_in, int | float) else 3600
        return {
            "access_token": grant["access_token"],
            "refresh_token": grant.get("refresh_token"),
            "expires_at": (self._clock.now() + timedelta(seconds=seconds)).isoformat(),
        }

    def _still_valid(self, token: Mapping[str, Any]) -> bool:
        try:
            expires = datetime.fromisoformat(str(token.get("expires_at")))
        except ValueError:
            return False
        expires = expires if expires.tzinfo else expires.replace(tzinfo=UTC)
        return bool(token.get("access_token")) and expires - self._clock.now() > EXPIRY_MARGIN

    async def _grant(self, http: httpx.AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await http.post(
                "/oauth/token",
                json={"client_id": self._client_id, "client_secret": self._client_secret, **body},
            )
        except httpx.HTTPError:
            raise Unavailable from None
        try:
            return self._token(_raise_for_login(response))
        except (ValueError, OverflowError, TypeError):
            raise Unavailable from None

    async def _login(
        self, http: httpx.AsyncClient, credentials: Credentials, stored: Mapping[str, Any] | None
    ) -> tuple[str, dict[str, Any] | None]:
        """(access token to use, token to store or None to keep the stored one)."""
        if stored and self._still_valid(stored):
            return str(stored["access_token"]), None
        refresh = stored.get("refresh_token") if stored else None
        if isinstance(refresh, str) and refresh:
            try:
                fresh = await self._grant(
                    http, {"grant_type": "refresh_token", "refresh_token": refresh}
                )
                return fresh["access_token"], fresh
            except (AuthFailed, Unavailable):
                pass  # an expired refresh token: fall back to the password, as the app does
        fresh = await self._grant(
            http,
            {
                "grant_type": "password",
                "username": credentials.email,
                "password": credentials.password,
            },
        )
        return fresh["access_token"], fresh

    async def check(self, credentials: Credentials) -> None:
        async with self._http(15.0) as http:
            await self._grant(
                http,
                {
                    "grant_type": "password",
                    "username": credentials.email,
                    "password": credentials.password,
                },
            )

    async def fetch(
        self, days: Sequence[date], credentials: Credentials, token: Mapping[str, Any] | None
    ) -> tuple[YazioBundle, dict[str, Any] | None]:
        async with self._http(20.0) as http:
            access, new_token = await self._login(http, credentials, token)
            headers = {"Authorization": f"Bearer {access}"}
            products: dict[str, Mapping[str, Any] | None] = {}
            recipes: dict[str, Mapping[str, Any] | None] = {}
            failures: list[str] = []
            out: list[tuple[date, tuple[YazioItem, ...]]] = []
            try:
                for day in days:
                    try:
                        items = await self._day(http, headers, day, products, recipes, failures)
                    except _Stop:
                        raise
                    except Exception:  # provider/parsing failures must not discard refreshed tokens
                        failures.append(f"diary {day}")
                        continue
                    out.append((day, items))
            except _Stop:
                failures.append("rate_limited")
        return YazioBundle(tuple(out), tuple(dict.fromkeys(failures))), new_token

    async def _get(
        self, http: httpx.AsyncClient, path: str, headers: Mapping[str, str], **params: str
    ) -> Any:
        response = await http.get(path, headers=headers, params=params or None)
        if response.status_code == 429:
            raise _Stop
        response.raise_for_status()
        return response.json()

    async def _lookup(
        self,
        http: httpx.AsyncClient,
        headers: Mapping[str, str],
        path: str,
        cache: dict[str, Mapping[str, Any] | None],
        key: str,
        failures: list[str],
        label: str,
    ) -> Mapping[str, Any] | None:
        if key not in cache:
            try:
                found = await self._get(http, f"{path}/{key}", headers)
                cache[key] = found if isinstance(found, dict) else None
            except (httpx.HTTPError, ValueError):
                cache[key] = None
        if cache[key] is None:
            failures.append(f"{label} {key}")
        return cache[key]

    async def _day(
        self,
        http: httpx.AsyncClient,
        headers: Mapping[str, str],
        day: date,
        products: dict[str, Mapping[str, Any] | None],
        recipes: dict[str, Mapping[str, Any] | None],
        failures: list[str],
    ) -> tuple[YazioItem, ...]:
        diary = await self._get(http, "/user/consumed-items", headers, date=day.isoformat())
        items: list[YazioItem] = []
        for entry in diary.get("products") or []:
            pid = entry.get("product_id")
            if pid and (
                product := await self._lookup(
                    http, headers, "/products", products, str(pid), failures, "product"
                )
            ):
                items.append(item_from_product(entry, product))
        items += [item_from_simple(entry) for entry in diary.get("simple_products") or []]
        for entry in diary.get("recipe_portions") or []:
            rid = entry.get("recipe_id")
            if rid and (
                recipe := await self._lookup(
                    http, headers, "/recipes", recipes, str(rid), failures, "recipe"
                )
            ):
                items.append(item_from_recipe(entry, recipe))
        return tuple(items)
