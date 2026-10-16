# gateway/tests/unit/test_attention.py
import asyncio
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from gateway.attention import ATTENTION_AGENTS, AttentionDismissals, build_router
from shared.ports.skills import SkillReply, SkillUnavailable
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Attention
from shared.testing.fakes import (
    FakeSkillClient,
    FixedClock,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

from gateway import attention as attention_module

USER = uuid4()
NOW = datetime(2026, 10, 16, 22, 30, tzinfo=UTC)  # 01:30 on the 17th in Kyiv


async def me() -> UUID:
    return USER


class MemoryDismissals:
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, str], date] = {}

    async def active(self, user_id: UUID, today: date) -> set[str]:
        return {i for (u, i), until in self.rows.items() if u == user_id and until > today}

    async def dismiss(self, user_id: UUID, item_id: str, until: date) -> None:
        self.rows[(user_id, item_id)] = until


def entry(id: str, level: str = "normal", rank: int = 0, **kw: object) -> dict[str, object]:
    return {"id": id, "level": level, "rank": rank, "text": id, "action": {"type": "agent"}, **kw}


class SlowClient:
    async def call(self, **_: object) -> SkillReply:
        await asyncio.sleep(1)
        return SkillReply("", {"items": []})


def app(
    replies: dict[str, object], dismissals: MemoryDismissals | None = None, timeout_s: float = 3.0
):  # type: ignore[no-untyped-def]
    settings = InMemoryUserSettings()
    settings.seed(USER, timezone="Europe/Kyiv")
    dismissals = dismissals or MemoryDismissals()

    def responder(agent: str):  # type: ignore[no-untyped-def]
        def answer(skill, user, params, text):  # type: ignore[no-untyped-def]
            assert skill == Attention.ITEMS
            assert user == USER
            reply = replies.get(agent, {"items": []})
            if isinstance(reply, Exception):
                return reply
            return SkillReply("", reply)

        return answer

    fakes: dict[str, object] = {a: FakeSkillClient(responder(a)) for a in ATTENTION_AGENTS}
    for agent, reply in replies.items():
        if reply == "slow":
            fakes[agent] = SlowClient()
    api = FastAPI()
    api.include_router(
        build_router(
            fakes.__getitem__,
            InMemoryUnitOfWorkFactory(
                {UserSettingsRepository: settings, AttentionDismissals: dismissals}
            ),
            FixedClock(NOW),
            me,
            timeout_s=timeout_s,
        )
    )
    return api, dismissals


async def get(api: FastAPI, path: str = "/me/attention", method: str = "GET") -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://t") as c:
        return await c.request(method, path)


async def test_sorts_across_agents_by_level_rank_then_agent_order() -> None:
    api, _ = app(
        {
            "workout": {"items": [entry("workout:plan:x", "high", -5)]},
            "kitchen": {
                "items": [
                    entry("kitchen:expired:a", "critical", -2),
                    entry("kitchen:today:d", "high", 0),
                ]
            },
            "mood": {"items": [entry("mood:checkin:x", "normal", -4)]},
        }
    )
    body = (await get(api)).json()
    assert [(i["agent"], i["id"]) for i in body["items"]] == [
        ("kitchen", "kitchen:expired:a"),
        ("workout", "workout:plan:x"),
        ("kitchen", "kitchen:today:d"),
        ("mood", "mood:checkin:x"),
    ]
    assert body["unavailable"] == []


async def test_dismissed_items_are_hidden_but_critical_never() -> None:
    dismissals = MemoryDismissals()
    dismissals.rows[(USER, "kitchen:today:d")] = date(2026, 10, 18)
    dismissals.rows[(USER, "kitchen:expired:a")] = date(2026, 10, 18)
    api, _ = app(
        {
            "kitchen": {
                "items": [entry("kitchen:expired:a", "critical"), entry("kitchen:today:d", "high")]
            }
        },
        dismissals,
    )
    assert [i["id"] for i in (await get(api)).json()["items"]] == ["kitchen:expired:a"]


async def test_malformed_agent_goes_unavailable_others_served() -> None:
    api, _ = app(
        {
            "sleep": {"items": [entry("sleep:x:1", "urgent")]},
            "mood": {"items": [entry(f"mood:x:{n}") for n in range(11)]},
            "body": SkillUnavailable("down"),
            "habits": "slow",
            "workout": {"items": [entry("workout:plan:x")]},
        },
        timeout_s=0.05,
    )
    body = (await get(api)).json()
    assert [i["id"] for i in body["items"]] == ["workout:plan:x"]
    assert set(body["unavailable"]) == {"sleep", "mood", "body", "habits"}


@pytest.mark.parametrize(
    ("reply", "reason"),
    [
        ({"items": "nope"}, "not_a_list"),
        ("nope", "not_a_list"),
        ({"items": [entry(f"sleep:x:{n}") for n in range(11)]}, "too_many"),
        ({"items": ["sleep:x:1"]}, "not_an_object"),
        ({"items": [entry("sleep:x:1", "urgent")]}, "invalid_item"),
        ({"items": [entry("mood:x:1")]}, "wrong_agent"),
    ],
)
async def test_malformed_reply_is_logged_with_a_reason(
    monkeypatch: pytest.MonkeyPatch, reply: object, reason: str
) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    class Logger:
        def warning(self, event: str, **fields: object) -> None:
            events.append((event, fields))

    monkeypatch.setattr(attention_module, "logger", Logger())
    api, _ = app({"sleep": reply})
    assert (await get(api)).json()["unavailable"] == ["sleep"]
    assert events == [("attention_agent_malformed", {"agent": "sleep", "reason": reason})]


async def test_dismiss_uses_user_local_date() -> None:
    api, dismissals = app({"kitchen": {"items": [entry("kitchen:today:d", "high")]}})
    response = await get(api, "/me/attention/kitchen:today:d/dismiss", "POST")
    assert response.status_code == 204
    assert dismissals.rows[(USER, "kitchen:today:d")] == date(2026, 10, 18)  # Kyiv is on the 17th


async def test_dismiss_accepts_colon_ids_percent_encoded() -> None:
    api, dismissals = app({"workout": {"items": [entry("workout:plan:2026-10-11")]}})
    response = await get(api, "/me/attention/workout%3Aplan%3A2026-10-11/dismiss", "POST")
    assert response.status_code == 204
    assert (USER, "workout:plan:2026-10-11") in dismissals.rows


async def test_dismiss_errors() -> None:
    api, dismissals = app(
        {
            "kitchen": {"items": [entry("kitchen:expired:a", "critical")]},
            "body": SkillUnavailable("x"),
        }
    )
    assert (await get(api, "/me/attention/kitchen:expired:a/dismiss", "POST")).status_code == 409
    assert (await get(api, "/me/attention/kitchen:gone:z/dismiss", "POST")).status_code == 404
    assert (await get(api, "/me/attention/finance:x:1/dismiss", "POST")).status_code == 404
    assert (await get(api, "/me/attention/body:weigh:x/dismiss", "POST")).status_code == 503
    assert dismissals.rows == {}
