from datetime import UTC, date, datetime
from uuid import uuid4

from shared.a2a.request import SkillRequest
from shared.attention import (
    AttentionAction,
    AttentionContext,
    AttentionItem,
    AttentionSkill,
    attention_result,
    days_since,
)
from shared.ports.translator import DateStyle
from shared.ports.uow import UnitOfWork
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Attention
from shared.testing.attention_contract import assert_attention_contract
from shared.testing.fakes import FixedClock, InMemoryUnitOfWorkFactory, InMemoryUserSettings

USER = uuid4()
NOW = datetime(2026, 10, 16, 21, 30, tzinfo=UTC)  # 00:30 on the 17th in Kyiv


class EchoTranslator:
    def t(self, key: str, locale: str, /, **params: object) -> str:
        return f"{locale}:{key}"

    def number(self, value: float, locale: str, *, digits: int = 0) -> str:
        return str(value)

    def date(self, value: date, locale: str, *, style: DateStyle = "medium") -> str:
        return value.isoformat()


def item(id: str, level: str, rank: int = 0, **kw: object) -> AttentionItem:
    return AttentionItem(id, level, rank, "text", AttentionAction("agent"), **kw)  # type: ignore[arg-type]


def test_result_sorts_by_level_then_rank_then_id_and_caps() -> None:
    items = [item(f"a:n:{i}", "normal", i) for i in range(12)] + [
        item("a:h:2", "high", 2),
        item("a:h:1", "high", 1),
        item("a:c:9", "critical", 9),
    ]
    data = attention_result(items).data
    assert_attention_contract(data)
    ids = [i["id"] for i in data["items"]]  # type: ignore[index]
    assert ids[:3] == ["a:c:9", "a:h:1", "a:h:2"]
    assert len(ids) == 10


def test_to_data_clips_text_and_detail_and_omits_empty_detail() -> None:
    long = AttentionItem(
        "a:x:1", "high", 0, "t" * 200, AttentionAction("task", "go"), detail="d" * 300
    )
    out = long.to_data()
    assert len(out["text"]) == 80  # type: ignore[arg-type]
    assert out["text"].endswith("…")  # type: ignore[attr-defined]
    assert len(out["detail"]) == 140  # type: ignore[arg-type]
    assert out["action"] == {"type": "task", "prompt": "go"}
    assert "detail" not in item("a:x:2", "normal").to_data()
    assert item("a:x:2", "normal").to_data()["action"] == {"type": "agent"}


async def test_skill_builds_context_in_user_zone_and_locale() -> None:
    settings = InMemoryUserSettings()
    settings.seed(USER, timezone="Europe/Kyiv", locale="ru")
    seen: list[AttentionContext] = []

    async def collect(tx: UnitOfWork, ctx: AttentionContext) -> list[AttentionItem]:
        seen.append(ctx)
        return [AttentionItem("a:x:1", "normal", 0, ctx.t("k"), AttentionAction("agent"))]

    skill = AttentionSkill(
        uow=InMemoryUnitOfWorkFactory({UserSettingsRepository: settings}),
        clock=FixedClock(NOW),
        translator=EchoTranslator(),
        default_locale="en",
        collect=collect,
    )
    result = await skill(SkillRequest("t", "c", "", USER, Attention.ITEMS, None, False, {}), ())
    assert_attention_contract(result.data)
    [ctx] = seen
    assert ctx.today.isoformat() == "2026-10-17"
    assert ctx.now_local.hour == 0
    assert result.data["items"][0]["text"] == "ru:k"  # type: ignore[index]
    assert days_since(ctx, datetime(2026, 10, 13, 20, 0, tzinfo=UTC)) == 4
