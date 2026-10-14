from __future__ import annotations

from datetime import datetime, timedelta

from shared.a2a.request import SkillRequest
from shared.analysis.prompt import PromptSection
from shared.analysis.skill import AnalysisData, LoadedData
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork
from shared.ports.users import UserSettings

from habits.application.ports import HabitRepository
from habits.domain.habit import Cadence, Habit, HabitCheck
from habits.domain.streak import by_day, current_streak, longest_streak

DEFAULT_DAYS = 30
EMPTY_TAIL = "There are not enough check-ins to analyze yet. Tell the user to log a few days first. Plain text, no markdown."


def _habit_line(h: Habit) -> str:
    cadence = "daily" if h.cadence is Cadence.DAILY else f"weekly: {', '.join(h.cadence_days)}"
    parts = [f"{h.name} ({h.kind.value})", cadence]
    if h.target_value is not None:
        parts.append(f"target={h.target_value:g}{h.unit or ''}")
    return "- " + " | ".join(parts)


class HabitData(AnalysisData):
    async def load(
        self, uow: UnitOfWork, request: SkillRequest, settings: UserSettings, now: datetime
    ) -> LoadedData:
        raw_days = request.params.get("days")
        days = (
            int(raw_days)
            if isinstance(raw_days, int | str) and str(raw_days).isdigit()
            else DEFAULT_DAYS
        )
        active = await uow.repo(HabitRepository).active()
        habit_id = request.params.get("habit_id")
        filters = {"habit_id": habit_id} if isinstance(habit_id, str) else None
        rows = await uow.repo(HealthLogRepository).recent(
            request.user_id, types=["habit"], since=now - timedelta(days=days), data_equals=filters
        )
        zone, today = settings.timezone, settings.today(now)
        names = {str(h.id): h.name for h in active}
        check_lines = []
        for r in rows:
            c = HabitCheck.from_row(r)
            bits = [names.get(c.habit_id) or str(r.data.get("name", "?"))]
            if c.value is not None:
                bits.append(f"{c.value:g}{c.unit or ''}")
            if c.note:
                bits.append(f'"{c.note[:40]}"')
            check_lines.append(f"- {c.at.astimezone(zone):%Y-%m-%d %H:%M} | " + " | ".join(bits))
        checks = [HabitCheck.from_row(r) for r in rows]
        streak_lines = []
        for h in active:
            grouped = by_day([c for c in checks if c.habit_id == str(h.id)], zone)
            streak_lines.append(
                f"- {h.name}: current={current_streak(h, grouped, today)}, "
                f"longest({days}d)={longest_streak(h, grouped, today - timedelta(days=days - 1), today)}"
            )
        sections = [
            PromptSection(
                "Active habits", "\n".join(_habit_line(h) for h in active) or "No active habits."
            ),
            PromptSection("Recent check-ins", "\n".join(check_lines) or "No check-ins in window."),
            PromptSection("Streaks", "\n".join(streak_lines) or "No streaks."),
        ]
        return LoadedData(sections, tail_override=None if rows else EMPTY_TAIL)
