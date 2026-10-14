from __future__ import annotations

from datetime import timedelta

from shared.a2a.executor import SkillResult
from shared.a2a.request import SkillRequest
from shared.ports.clock import Clock
from shared.ports.health_logs import HealthLogRepository
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettingsRepository

from habits.application.ports import HabitRepository
from habits.domain.habit import HabitCheck, Kind
from habits.domain.streak import by_day, current_streak, day_complete, today_total

WINDOW_DAYS = 180


class StreakSummary:
    """get_streak_summary: deterministic, no model."""

    def __init__(
        self, *, uow: UnitOfWorkFactory, clock: Clock, translator: Translator, default_locale: str
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._tr = translator
        self._default_locale = default_locale

    async def __call__(self, request: SkillRequest, consult: tuple[str, ...]) -> SkillResult:
        uid = request.user_id
        now = self._clock.now()
        async with self._uow.for_user(uid) as tx:
            settings = await tx.repo(UserSettingsRepository).get(uid)
            active = await tx.repo(HabitRepository).active()
            rows = await tx.repo(HealthLogRepository).recent(
                uid, types=["habit"], since=now - timedelta(days=WINDOW_DAYS)
            )
        locale = settings.locale or self._default_locale
        if not active:
            return SkillResult(output=self._tr.t("habits.streak.none", locale))
        today = settings.today(now)
        checks = [HabitCheck.from_row(r) for r in rows]
        parts = []
        for habit in active:
            days = by_day([c for c in checks if c.habit_id == str(habit.id)], settings.timezone)
            todays = days.get(today, [])
            streak = current_streak(habit, days, today)
            progress = ""
            if habit.kind is Kind.QUANTITATIVE and habit.target_value is not None:
                progress = self._tr.t(
                    "habits.streak.progress",
                    locale,
                    done=f"{today_total(habit, todays):g}",
                    target=f"{habit.target_value:g}",
                    unit=habit.unit or "",
                )
            parts.append(
                self._tr.t(
                    "habits.streak.line",
                    locale,
                    mark="✅" if day_complete(habit, todays) else "⬜",
                    name=habit.name,
                    days=self._tr.t("habits.days", locale, count=streak, n=streak),
                    progress=progress,
                )
            )
        return SkillResult(output=" · ".join(parts))
