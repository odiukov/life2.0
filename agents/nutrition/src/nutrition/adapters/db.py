"""Nutrition repositories over health_logs and users (row-level security applies)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared.adapters.db.profile import SqlBodyProfiles
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.db.users import SqlUserSettings
from shared.domain.energy import BodyProfile
from shared.ports.users import UserSettingsRepository
from shared.schema.tables import health_logs, users
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from nutrition.application.models import BodyComposition, UserProfile
from nutrition.application.ports import BodyMetricsRepository, MealRepository, ProfileRepository
from nutrition.domain.day import resolve_zone
from nutrition.domain.meal import CHAT_SOURCE, YAZIO_SOURCE, Macros, Meal, MealItem, MealType

AGENT = "nutrition"
MEAL = "meal"
_ONE_US = timedelta(microseconds=1)
_MAX_SHIFTS = 1000
_LOCALES = {"ru", "en"}


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _opt_num(value: object) -> float | None:
    return None if value is None else _num(value)


def _macros(data: Mapping[str, Any]) -> Macros:
    return Macros(
        kcal=_num(data.get("kcal")),
        protein_g=_num(data.get("protein_g")),
        carbs_g=_num(data.get("carbs_g")),
        fat_g=_num(data.get("fat_g")),
    )


def meal_to_data(meal: Meal) -> dict[str, object]:
    """Encode the wire shape shared with the existing Yazio mapper."""

    def number(value: float) -> float | int:
        return int(value) if float(value).is_integer() else value

    return {
        "meal_type": meal.meal_type.value if meal.meal_type else None,
        "items": [
            {
                "name": item.name,
                "amount_g": number(item.amount_g) if item.amount_g is not None else None,
                "kcal": number(item.macros.kcal),
                "protein_g": number(item.macros.protein_g),
                "carbs_g": number(item.macros.carbs_g),
                "fat_g": number(item.macros.fat_g),
            }
            for item in meal.items
        ],
        "totals": {
            "kcal": number(meal.totals.kcal),
            "protein_g": number(meal.totals.protein_g),
            "carbs_g": number(meal.totals.carbs_g),
            "fat_g": number(meal.totals.fat_g),
        },
    }


def _meal_from_row(row: Row[Any, Any, Any]) -> Meal:
    data: Mapping[str, Any] = row.data or {}
    items = tuple(
        MealItem(
            name=str(i.get("name", "")), amount_g=_opt_num(i.get("amount_g")), macros=_macros(i)
        )
        for i in data.get("items") or []
        if isinstance(i, Mapping)
    )
    totals = data.get("totals")
    meal_type = data.get("meal_type")
    return Meal(
        recorded_at=row.recorded_at,
        items=items,
        totals=_macros(totals)
        if isinstance(totals, Mapping)
        else sum((i.macros for i in items), Macros()),
        meal_type=MealType(meal_type)
        if isinstance(meal_type, str) and meal_type in {m.value for m in MealType}
        else None,
        source=row.source,
    )


def _profile_from_row(row: Row[Any, Any]) -> UserProfile:
    """Normalize database results, including missing or invalid timezone values."""
    prefs: Mapping[str, Any] = row.preferences if isinstance(row.preferences, Mapping) else {}
    locale = prefs.get("locale")
    body = prefs.get("body_profile")
    return UserProfile(
        timezone=resolve_zone(row.timezone),
        locale=locale if isinstance(locale, str) and locale in _LOCALES else None,
        body=BodyProfile.from_mapping(body if isinstance(body, Mapping) else {}),
    )


_MEAL_COLUMNS = (health_logs.c.recorded_at, health_logs.c.source, health_logs.c.data)


class SqlMealRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, user_id: UUID, meal: Meal) -> Meal:
        # Shift UTC instants: arithmetic on a local DST fold can change the instant.
        when = meal.recorded_at.astimezone(UTC)
        data = meal_to_data(meal)
        for _ in range(_MAX_SHIFTS):
            statement = (
                insert(health_logs)
                .values(
                    user_id=user_id,
                    agent=AGENT,
                    type=MEAL,
                    source=meal.source,
                    recorded_at=when,
                    data=data,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        health_logs.c.user_id,
                        health_logs.c.source,
                        health_logs.c.type,
                        health_logs.c.recorded_at,
                    ]
                )
                .returning(health_logs.c.id)
            )
            # DO NOTHING leaves this transaction usable on a unique-key collision.
            if (await self._conn.execute(statement)).first() is not None:
                return meal.with_recorded_at(when)
            when += _ONE_US
        raise RuntimeError("no free timestamp for the meal")

    async def between(self, user_id: UUID, start: datetime, end: datetime) -> list[Meal]:
        query = (
            select(*_MEAL_COLUMNS)
            .where(
                health_logs.c.user_id == user_id,
                health_logs.c.agent == AGENT,
                health_logs.c.type == MEAL,
                health_logs.c.source.in_((CHAT_SOURCE, YAZIO_SOURCE)),
                health_logs.c.recorded_at >= start,
                health_logs.c.recorded_at < end,
            )
            .order_by(health_logs.c.recorded_at)
        )
        return [_meal_from_row(row) for row in await self._conn.execute(query)]

    async def recent(self, user_id: UUID, limit: int) -> list[Meal]:
        query = (
            select(*_MEAL_COLUMNS)
            .where(
                health_logs.c.user_id == user_id,
                health_logs.c.agent == AGENT,
                health_logs.c.type == MEAL,
            )
            .order_by(health_logs.c.recorded_at.desc())
            .limit(limit)
        )
        return [_meal_from_row(row) for row in await self._conn.execute(query)]


class SqlProfileRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def get(self, user_id: UUID) -> UserProfile:
        row = (
            await self._conn.execute(
                select(users.c.timezone, users.c.preferences).where(users.c.id == user_id)
            )
        ).one_or_none()
        return UserProfile.default() if row is None else _profile_from_row(row)

    async def update_body_profile(
        self, user_id: UUID, changes: Mapping[str, object]
    ) -> BodyProfile:
        return BodyProfile.from_mapping(await SqlBodyProfiles(self._conn).update(user_id, changes))


class SqlBodyMetricsRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def latest(self, user_id: UUID) -> BodyComposition | None:
        # Historical rows used agent='workout'; current rows use 'body'. Filter by type.
        row = (
            await self._conn.execute(
                select(health_logs.c.recorded_at, health_logs.c.data)
                .where(health_logs.c.user_id == user_id, health_logs.c.type == "body_composition")
                .order_by(health_logs.c.recorded_at.desc())
                .limit(1)
            )
        ).one_or_none()
        if row is None:
            return None
        data: Mapping[str, Any] = row.data or {}
        return BodyComposition(
            recorded_at=row.recorded_at,
            weight_kg=_opt_num(data.get("weight_kg")),
            body_fat_pct=_opt_num(data.get("body_fat_pct")),
            bmr_kcal=_opt_num(data.get("bmr_kcal")),
        )


def nutrition_uow(engine: AsyncEngine) -> SqlUnitOfWorkFactory:
    return SqlUnitOfWorkFactory(
        engine,
        {
            MealRepository: SqlMealRepository,
            ProfileRepository: SqlProfileRepository,
            BodyMetricsRepository: SqlBodyMetricsRepository,
            UserSettingsRepository: SqlUserSettings,
        },
    )
