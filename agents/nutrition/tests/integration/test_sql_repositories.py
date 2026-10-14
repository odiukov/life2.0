import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from nutrition.adapters.db import _profile_from_row, nutrition_uow
from nutrition.application.ports import BodyMetricsRepository, MealRepository, ProfileRepository
from nutrition.domain.meal import CHAT_SOURCE, Macros, Meal, MealItem
from shared.adapters.db.engine import create_engine
from shared.config import DatabaseSettings
from shared.domain.energy import BodyProfile
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration
T0 = datetime(2026, 10, 13, 8, tzinfo=UTC)


@pytest.fixture
async def env(clean_db: PostgresUrls):
    admin = create_async_engine(clean_db.admin)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    a, b = uuid4(), uuid4()
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name) VALUES (:a, 'a'), (:b, 'b')"), {"a": a, "b": b}
        )
    try:
        yield admin, nutrition_uow(engine), a, b
    finally:
        await engine.dispose()
        await admin.dispose()


def meal(kcal: float = 300) -> Meal:
    return Meal.from_items(
        recorded_at=T0,
        items=(MealItem("омлет", 180, Macros(kcal=kcal, protein_g=20, carbs_g=2, fat_g=22)),),
        meal_type=None,
        source=CHAT_SOURCE,
    )


async def test_rls_blocks_writing_a_meal_for_someone_else(env) -> None:
    _, uow, a, b = env
    with pytest.raises(DBAPIError, match="row-level security"):
        async with uow.for_user(a) as tx:
            await tx.repo(MealRepository).add(b, meal())


async def test_app_rw_cannot_read_other_users_even_when_requested_explicitly(env) -> None:
    admin, uow, a, b = env
    async with uow.for_user(b) as tx:
        await tx.repo(MealRepository).add(b, meal())
        await tx.repo(ProfileRepository).update_body_profile(b, {"age": 30})
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO health_logs (user_id, agent, type, data) "
                "VALUES (:uid, 'body', 'body_composition', CAST(:data AS jsonb))"
            ),
            {"uid": b, "data": json.dumps({"weight_kg": 80})},
        )
    async with uow.for_user(a) as tx:
        role = (
            await tx.connection.execute(
                text(
                    "SELECT current_user AS name, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).one()
        assert role.name == "app_rw"
        assert role.rolbypassrls is False
        assert await tx.repo(MealRepository).recent(b, 10) == []
        assert await tx.repo(MealRepository).between(b, T0, T0 + timedelta(days=1)) == []
        assert (await tx.repo(ProfileRepository).get(b)).body == BodyProfile()
        assert await tx.repo(BodyMetricsRepository).latest(b) is None


async def test_rls_blocks_updating_another_users_profile(env) -> None:
    admin, uow, a, b = env
    with pytest.raises(DBAPIError, match="row-level security"):
        async with uow.for_user(a) as tx:
            await tx.repo(ProfileRepository).update_body_profile(b, {"age": 31})
    async with admin.connect() as conn:
        prefs = (
            await conn.execute(text("SELECT preferences FROM users WHERE id = :uid"), {"uid": b})
        ).scalar_one()
    assert prefs == {}


async def test_reads_rows_written_by_the_yazio_sync_service(env) -> None:
    admin, uow, a, _ = env
    yazio = {
        "meal_type": "breakfast",
        "items": [
            {
                "name": "Oatmeal",
                "amount_g": 80,
                "kcal": 300,
                "protein_g": 10,
                "carbs_g": 50,
                "fat_g": 6,
            }
        ],
        "totals": {"kcal": 300.0, "protein_g": 10.0, "carbs_g": 50.0, "fat_g": 6.0},
        "date": "2026-10-13",
    }
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO health_logs (user_id, agent, type, source, recorded_at, data) "
                "VALUES (:uid, 'nutrition', 'meal', 'yazio', :at, CAST(:data AS jsonb))"
            ),
            {"uid": a, "at": T0, "data": json.dumps(yazio)},
        )
    async with uow.for_user(a) as tx:
        [found] = await tx.repo(MealRepository).recent(a, 5)
    assert found.source == "yazio"
    assert found.items[0].name == "Oatmeal"
    assert found.items[0].amount_g == 80
    assert found.totals == Macros(kcal=300, protein_g=10, carbs_g=50, fat_g=6)
    assert found.meal_type is not None
    assert found.meal_type.value == "breakfast"


async def test_stored_rows_match_the_yazio_shape(env) -> None:
    admin, uow, a, _ = env
    async with uow.for_user(a) as tx:
        await tx.repo(MealRepository).add(a, meal())
    async with admin.connect() as conn:
        row = (await conn.execute(text("SELECT agent, type, source, data FROM health_logs"))).one()
    assert (row.agent, row.type, row.source) == ("nutrition", "meal", "chat")
    assert row.data == {
        "meal_type": None,
        "items": [
            {
                "name": "омлет",
                "amount_g": 180,
                "kcal": 300,
                "protein_g": 20,
                "carbs_g": 2,
                "fat_g": 22,
            }
        ],
        "totals": {"kcal": 300, "protein_g": 20, "carbs_g": 2, "fat_g": 22},
    }


async def test_collision_retry_keeps_transaction_usable_and_both_rows_persist(env) -> None:
    admin, uow, a, _ = env
    async with uow.for_user(a) as tx:
        repo = tx.repo(MealRepository)
        await repo.add(a, meal(100))
        shifted = await repo.add(a, meal(50))
        assert shifted.recorded_at == T0 + timedelta(microseconds=1)
        await tx.repo(ProfileRepository).update_body_profile(a, {"age": 31})
        assert (
            sum(m.totals.kcal for m in await repo.between(a, T0, T0 + timedelta(minutes=1))) == 150
        )
    async with admin.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT recorded_at, data FROM health_logs WHERE user_id = :uid ORDER BY recorded_at"
                ),
                {"uid": a},
            )
        ).all()
    assert [r.recorded_at for r in rows] == [T0, T0 + timedelta(microseconds=1)]
    assert [r.data["totals"]["kcal"] for r in rows] == [100, 50]
    async with uow.for_user(a) as tx:
        assert (await tx.repo(ProfileRepository).get(a)).body.age == 31


async def test_profile_update_preserves_unrelated_preferences_and_clears_none(env) -> None:
    admin, uow, a, _ = env
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "UPDATE users SET timezone = 'Europe/Lisbon', preferences = CAST(:prefs AS jsonb) "
                "WHERE id = :uid"
            ),
            {
                "uid": a,
                "prefs": json.dumps(
                    {
                        "locale": "en",
                        "notifications": {"enabled": True},
                        "body_profile": {"age": 30, "height_cm": 180},
                    }
                ),
            },
        )
    async with uow.for_user(a) as tx:
        merged = await tx.repo(ProfileRepository).update_body_profile(
            a, {"age": None, "height_cm": 181}
        )
    assert merged == BodyProfile(height_cm=181)
    async with admin.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT timezone, preferences FROM users WHERE id = :uid"), {"uid": a}
            )
        ).one()
    assert row.timezone == "Europe/Lisbon"
    assert row.preferences == {
        "locale": "en",
        "notifications": {"enabled": True},
        "body_profile": {"height_cm": 181},
    }


async def test_updating_unknown_user_creates_profile_and_malformed_body_can_be_replaced(
    env,
) -> None:
    admin, uow, _, _ = env
    uid = uuid4()
    async with uow.for_user(uid) as tx:
        assert await tx.repo(ProfileRepository).update_body_profile(
            uid, {"age": 30}
        ) == BodyProfile(age=30)
    async with admin.begin() as conn:
        await conn.execute(
            text('UPDATE users SET preferences = \'{"body_profile":"invalid"}\' WHERE id = :uid'),
            {"uid": uid},
        )
    async with uow.for_user(uid) as tx:
        assert await tx.repo(ProfileRepository).update_body_profile(
            uid, {"height_cm": 181}
        ) == BodyProfile(height_cm=181)


async def test_nullable_adapter_result_timezone_normalizes_to_utc_without_schema_changes(
    env,
) -> None:
    admin, _, _, _ = env
    async with admin.connect() as conn:
        row = (
            await conn.execute(text("SELECT NULL::text AS timezone, '{}'::jsonb AS preferences"))
        ).one()
        nullable = (
            await conn.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'timezone'"
                )
            )
        ).scalar_one()
    assert row.timezone is None
    assert _profile_from_row(row).timezone == ZoneInfo("UTC")
    assert nullable == "NO"


async def test_filters_agent_and_type_and_reads_historical_workout_body_rows(env) -> None:
    admin, uow, a, _ = env
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO health_logs (user_id, agent, type, source, recorded_at, data) VALUES "
                "(:uid, 'workout', 'meal', 'yazio', :at, '{}'), "
                "(:uid, 'nutrition', 'analysis', 'chat', :at, '{}'), "
                "(:uid, 'workout', 'body_composition', 'apple_health', :at, "
                "CAST(:data AS jsonb))"
            ),
            {
                "uid": a,
                "at": T0,
                "data": json.dumps({"weight_kg": 80, "body_fat_pct": None, "bmr_kcal": 1700}),
            },
        )
    async with uow.for_user(a) as tx:
        assert await tx.repo(MealRepository).recent(a, 10) == []
        assert await tx.repo(MealRepository).between(a, T0, T0 + timedelta(days=1)) == []
        body = await tx.repo(BodyMetricsRepository).latest(a)
    assert body is not None
    assert body.weight_kg == 80
    assert body.bmr_kcal == 1700
    assert body.body_fat_pct is None


async def test_legacy_meal_without_totals_sums_items_and_ignores_invalid_meal_type(env) -> None:
    admin, uow, a, _ = env
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO health_logs (user_id, agent, type, source, recorded_at, data) "
                "VALUES (:uid, 'nutrition', 'meal', 'yazio', :at, CAST(:data AS jsonb))"
            ),
            {
                "uid": a,
                "at": T0,
                "data": json.dumps(
                    {
                        "meal_type": {"invalid": True},
                        "items": [
                            {"name": "first", "kcal": "100.5", "amount_g": None},
                            {"name": "second", "kcal": 50, "protein_g": "invalid"},
                            None,
                        ],
                    }
                ),
            },
        )
    async with uow.for_user(a) as tx:
        [found] = await tx.repo(MealRepository).recent(a, 1)
    assert found.totals == Macros(kcal=150.5)
    assert found.meal_type is None
    assert len(found.items) == 2
    assert found.items[0].amount_g is None


async def test_uow_rolls_back_meal_and_profile_together(env) -> None:
    _, uow, a, _ = env

    async def abort_transaction() -> None:
        async with uow.for_user(a) as tx:
            await tx.repo(MealRepository).add(a, meal())
            await tx.repo(ProfileRepository).update_body_profile(a, {"age": 31})
            raise RuntimeError("abort")

    with pytest.raises(RuntimeError, match="abort"):
        await abort_transaction()
    async with uow.for_user(a) as tx:
        assert await tx.repo(MealRepository).recent(a, 10) == []
        assert (await tx.repo(ProfileRepository).get(a)).body == BodyProfile()
