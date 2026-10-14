from __future__ import annotations

from typing import Literal

from sync.application.ports import Credentials, GarminClient, IntegrationError, Service, YazioClient

CheckStatus = Literal["ok", "disabled", "auth_failed", "rate_limited", "unavailable"]


class CheckCredentials:
    """Log in once to verify what the user typed; stores nothing."""

    def __init__(self, *, garmin: GarminClient, yazio: YazioClient | None) -> None:
        self._garmin = garmin
        self._yazio = yazio

    async def __call__(self, service: Service, credentials: Credentials) -> CheckStatus:
        client = self._garmin if service == "garmin" else self._yazio
        if client is None:
            return "disabled"
        try:
            await client.check(credentials)
        except IntegrationError as error:
            return error.code
        return "ok"
