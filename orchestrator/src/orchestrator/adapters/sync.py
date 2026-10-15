from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

import httpx

from orchestrator.application.ports import SyncUnavailable


class HttpHealthSync:
    def __init__(self, http: httpx.AsyncClient, sync_url: str, *, timeout_s: float = 120.0) -> None:
        self._http, self._url, self._timeout = http, sync_url.rstrip("/"), timeout_s

    async def sync_user(self, user_id: UUID) -> list[Mapping[str, object]]:
        try:
            response = await self._http.post(
                f"{self._url}/sync/user", json={"user_id": str(user_id)}, timeout=self._timeout
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("results"), list):
                raise ValueError("invalid_results")
            results: list[Mapping[str, object]] = []
            for row in body["results"]:
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("service"), str)
                    or not isinstance(row.get("status"), str)
                    or not isinstance(row.get("written"), int)
                    or isinstance(row.get("written"), bool)
                ):
                    raise ValueError("invalid_result")
                results.append(row)
            return results
        except (httpx.HTTPError, KeyError, ValueError):
            raise SyncUnavailable from None
