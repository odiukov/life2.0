from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from body.application.data import BodyData
from shared.a2a.request import SkillRequest
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettings
from shared.testing.fakes import InMemoryHealthLogs, InMemoryUnitOfWorkFactory

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


def req(user):  # type: ignore[no-untyped-def]
    return SkillRequest(
        task_id="t",
        context_id="c",
        text="вес?",
        user_id=user,
        skill_id="get_latest_body",
        for_date=None,
        is_peer_call=False,
    )


async def load(logs: InMemoryHealthLogs, user):  # type: ignore[no-untyped-def]
    uow = InMemoryUnitOfWorkFactory({HealthLogRepository: logs})
    async with uow.for_user(user) as tx:
        return await BodyData().load(tx, req(user), UserSettings(ZoneInfo("UTC"), None), NOW)


async def test_reads_only_body_composition_from_any_agent_newest_first_capped_at_30() -> None:
    logs, user = InMemoryHealthLogs(), uuid4()
    for i in range(32):
        logs.seed(
            user,
            HealthLogRow(
                "body_composition",
                NOW - timedelta(days=i),
                {"weight_kg": 80 + i / 10},
                agent="workout" if i % 2 else "body",
            ),
        )
    logs.seed(user, HealthLogRow("sleep_session", NOW, {"duration_seconds": 1}, agent="sleep"))
    logs.seed(user, HealthLogRow("nutrition", NOW, {"calories": 2100}, agent="nutrition"))
    logs.seed(user, HealthLogRow("activity", NOW, {"duration_seconds": 600}, agent="workout"))
    loaded = await load(logs, user)
    [section] = loaded.sections
    assert section.title == "Body composition history (latest 30)"
    lines = section.body.splitlines()
    assert len(lines) == 30
    assert lines[0].startswith("- 2026-10-13 | weight=80kg")
    assert "calories" not in section.body
    assert lines[-1].startswith("- 2026-09-14 | weight=82.9kg")
    assert "duration" not in section.body  # no cross-domain reads


async def test_empty_history_asks_for_an_upload() -> None:
    loaded = await load(InMemoryHealthLogs(), uuid4())
    assert (
        loaded.sections[0].body
        == "No body composition measurements yet — ask the user to upload a ViHealth PDF."
    )
