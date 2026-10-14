from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)
from sync.adapters.garmin_client import GarminConnectClient
from sync.application.ports import AuthFailed, Credentials, RateLimited, Unavailable

CREDS = Credentials("person@example.com", "hunter2")
DAYS = [date(2026, 10, 13), date(2026, 10, 12)]
TOKEN = '{"di_token": "x"}'


class FakeTokens:
    def __init__(
        self, dumped: str | Exception, login: Callable[[], tuple[str | None, None]]
    ) -> None:
        self.dumped = dumped
        self._login = login

    def login(self, email: str, password: str, *, return_on_mfa: bool) -> tuple[str | None, None]:
        return self._login()

    def dumps(self) -> str:
        if isinstance(self.dumped, Exception):
            raise self.dumped
        return self.dumped


class FakeGarmin:
    """Records calls; `fail` maps a method name to the exception it raises (optionally only for one date)."""

    def __init__(
        self,
        *,
        login: Exception | None = None,
        mfa: bool = False,
        fail: dict[str, Exception] | None = None,
        dumped: str | Exception = '{"di_token": "new"}',
    ) -> None:
        self.login_error, self.mfa, self.fail = login, mfa, fail or {}
        self.client = FakeTokens(dumped, self.login)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __call__(self, email: str, password: str) -> "FakeGarmin":
        self.calls.append(("init", (email,)))
        return self

    def login(self, tokenstore: str | None = None) -> tuple[str | None, None]:
        self.calls.append(("login", (tokenstore,)))
        if self.login_error:
            raise self.login_error
        return ("needs_mfa" if self.mfa else None), None

    def _load_profile_and_settings(self) -> None:
        pass

    def _call(self, name: str, *args: Any) -> Any:
        self.calls.append((name, args))
        error = self.fail.get(f"{name} {args[0]}") or self.fail.get(name)
        if error:
            raise error
        return [{"activityId": 1}] if name == "get_activities_by_date" else {"for": args[0]}

    def get_sleep_data(self, day: str) -> Any:
        return self._call("get_sleep_data", day)

    def get_stats(self, day: str) -> Any:
        return self._call("get_stats", day)

    def get_hrv_data(self, day: str) -> Any:
        return self._call("get_hrv_data", day)

    def get_activities_by_date(self, start: str, end: str) -> Any:
        return self._call("get_activities_by_date", start, end)


async def test_fetches_every_part_newest_first_and_returns_the_new_token() -> None:
    fake = FakeGarmin()
    bundle, token = await GarminConnectClient(fake).fetch(DAYS, CREDS, TOKEN)
    assert ("login", (TOKEN,)) in fake.calls
    assert [day for day, _ in bundle.sleep] == DAYS
    assert bundle.stats[0] == (date(2026, 10, 13), {"for": "2026-10-13"})
    assert [day for day, _ in bundle.hrv] == DAYS
    assert ("get_activities_by_date", ("2026-10-12", "2026-10-13")) in fake.calls
    assert bundle.activities == ({"activityId": 1},)
    assert bundle.failures == ()
    assert token == '{"di_token": "new"}'


@pytest.mark.parametrize("stored", [None, "", "/home/someone/.garminconnect", "not json"])
async def test_only_inline_json_tokens_reach_login(stored: str | None) -> None:
    # garminconnect treats a non-JSON tokenstore as a file path; never let a stored value point at the filesystem.
    fake = FakeGarmin()
    await GarminConnectClient(fake).fetch(DAYS, CREDS, stored)
    assert ("login", (None,)) in fake.calls


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GarminConnectAuthenticationError("bad password for person@example.com"), AuthFailed),
        (GarminConnectTooManyRequestsError("429 for person@example.com"), RateLimited),
        (GarminConnectConnectionError("dns person@example.com"), Unavailable),
        (RuntimeError("anything else person@example.com"), Unavailable),
    ],
)
async def test_login_errors_become_codes_without_text(
    error: Exception, expected: type[Exception]
) -> None:
    with pytest.raises(expected) as caught:
        await GarminConnectClient(FakeGarmin(login=error)).fetch(DAYS, CREDS, None)
    assert str(caught.value) == ""
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__


async def test_mfa_accounts_cannot_sync_unattended() -> None:
    with pytest.raises(AuthFailed):
        await GarminConnectClient(FakeGarmin(mfa=True)).fetch(DAYS, CREDS, None)


async def test_part_failures_are_named_not_described_and_not_found_is_no_data() -> None:
    fake = FakeGarmin(
        fail={
            "get_sleep_data 2026-10-12": GarminConnectConnectionError("secret text"),
            "get_hrv_data": GarminConnectNotFoundError("no hrv on this device"),
        }
    )
    bundle, token = await GarminConnectClient(fake).fetch(DAYS, CREDS, None)
    assert bundle.failures == ("sleep 2026-10-12",)
    assert [day for day, _ in bundle.sleep] == [date(2026, 10, 13)]
    assert bundle.hrv == ()
    assert token is not None


async def test_rate_limit_mid_fetch_stops_calling_and_keeps_the_token() -> None:
    fake = FakeGarmin(
        fail={"get_sleep_data 2026-10-12": GarminConnectTooManyRequestsError("slow down")}
    )
    bundle, token = await GarminConnectClient(fake).fetch(DAYS, CREDS, None)
    assert bundle.failures == ("rate_limited",)
    assert [name for name, _ in fake.calls][-1] == "get_sleep_data"  # nothing after the 429
    assert token == '{"di_token": "new"}'


async def test_unserializable_token_means_keep_the_stored_one() -> None:
    _, token = await GarminConnectClient(FakeGarmin(dumped=RuntimeError("x"))).fetch(
        DAYS, CREDS, TOKEN
    )
    assert token is None


@pytest.mark.parametrize("mfa", [False, True])
async def test_check_uses_direct_login_and_rejects_mfa(mfa: bool) -> None:
    from unittest.mock import Mock

    api = Mock()
    api.client.login.return_value = ("needs_mfa" if mfa else None, None)
    adapter = GarminConnectClient(lambda email, password: api)
    if mfa:
        with pytest.raises(AuthFailed):
            await adapter.check(CREDS)
    else:
        await adapter.check(CREDS)
    api.client.login.assert_called_once_with(CREDS.email, CREDS.password, return_on_mfa=True)
    api.login.assert_not_called()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GarminConnectAuthenticationError("x"), AuthFailed),
        (GarminConnectTooManyRequestsError("x"), RateLimited),
        (RuntimeError("x"), Unavailable),
    ],
)
async def test_check_maps_direct_login_errors(error: Exception, expected: type[Exception]) -> None:
    from unittest.mock import Mock

    api = Mock()
    api.client.login.side_effect = error
    with pytest.raises(expected) as caught:
        await GarminConnectClient(lambda email, password: api).check(CREDS)
    assert str(caught.value) == ""
    assert caught.value.__suppress_context__


def test_credentials_hide_the_password() -> None:
    assert "hunter2" not in repr(CREDS)
    assert Credentials.from_payload(
        {"email": "a@b.c", "password": "p", "garmin_token": "t"}
    ) == Credentials("a@b.c", "p")
    assert Credentials.from_payload({"email": "a@b.c"}) is None
    assert Credentials.from_payload({"email": "", "password": "p"}) is None


async def test_constructor_failure_is_sanitized() -> None:
    def broken(email: str, password: str) -> Any:
        raise RuntimeError("provider private detail")

    with pytest.raises(Unavailable) as caught:
        await GarminConnectClient(broken).check(CREDS)
    assert str(caught.value) == ""
    assert caught.value.__suppress_context__


async def test_malformed_activities_keep_refreshed_token() -> None:
    class MalformedGarmin(FakeGarmin):
        def get_activities_by_date(self, start: str, end: str) -> Any:
            return 42

    bundle, token = await GarminConnectClient(MalformedGarmin()).fetch(DAYS, CREDS, None)
    assert bundle.failures == ("activities",)
    assert token == '{"di_token": "new"}'
    assert len(bundle.stats) == 2


@pytest.mark.parametrize("environment_token", [TOKEN, "/unused/garmin-token-store"])
@pytest.mark.parametrize("operation", ["check", "fetch_without_token", "fetch_rejected_token"])
async def test_fresh_login_validates_credentials_despite_environment_tokens(
    monkeypatch: pytest.MonkeyPatch, environment_token: str, operation: str
) -> None:
    from garminconnect import Garmin
    from garminconnect.client import Client

    monkeypatch.setenv("GARMINTOKENS", environment_token)
    loaded: list[str] = []
    attempted: list[tuple[str, str]] = []

    def load(_self: Any, token: str) -> None:
        loaded.append(token)

    def reject(_self: Any, email: str, password: str) -> None:
        attempted.append((email, password))
        raise GarminConnectAuthenticationError("invalid credentials")

    monkeypatch.setattr(Client, "load", load)
    monkeypatch.setattr(Client, "loads", load)
    monkeypatch.setattr(Client, "_mobile_login_cffi", reject)
    monkeypatch.setattr(Garmin, "_load_profile_and_settings", lambda self: None)
    for method in ("get_sleep_data", "get_stats", "get_hrv_data", "get_activities_by_date"):
        monkeypatch.setattr(Garmin, method, lambda self, *args: None)
    adapter = GarminConnectClient()
    token = None if operation == "fetch_without_token" else "/rejected/token/path"
    call = adapter.check(CREDS) if operation == "check" else adapter.fetch(DAYS, CREDS, token)
    with pytest.raises(AuthFailed):
        await call
    assert attempted == [(CREDS.email, CREDS.password)]
    assert loaded == []


async def test_fresh_fetch_loads_profile_after_direct_credentials_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from garminconnect import Garmin
    from garminconnect.client import Client

    calls: list[str] = []
    monkeypatch.setenv("GARMINTOKENS", "/unused/garmin-token-store")
    monkeypatch.setattr(
        Client, "_mobile_login_cffi", lambda self, email, password: calls.append("credentials")
    )
    monkeypatch.setattr(Client, "_verify_token", lambda self: True)
    monkeypatch.setattr(Garmin, "_load_profile_and_settings", lambda self: calls.append("profile"))
    monkeypatch.setattr(Client, "dumps", lambda self: TOKEN)
    for method in ("get_sleep_data", "get_stats", "get_hrv_data", "get_activities_by_date"):
        monkeypatch.setattr(Garmin, method, lambda self, *args: None)
    bundle, token = await GarminConnectClient().fetch(DAYS, CREDS, None)
    assert calls == ["credentials", "profile"]
    assert bundle.failures == ()
    assert token == TOKEN
