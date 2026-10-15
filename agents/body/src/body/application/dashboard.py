"""dashboard.card for body: featured weight trend + tile. (No detail: the app has no body detail.)"""

from __future__ import annotations

from datetime import timedelta

from shared.dashboard import DashboardContext, empty_card
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.uow import UnitOfWork


def _age_label(days: int) -> str:
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


def featured(rows: list[HealthLogRow], ctx: DashboardContext) -> dict[str, object] | None:
    if len(rows) < 2:
        return None
    latest = rows[0]
    data = latest.data
    if data.get("weight_kg") is None:
        return None
    age = (ctx.now - latest.recorded_at).days
    if age > 60:
        return None
    target = latest.recorded_at - timedelta(days=30)
    previous = next((r for r in rows[1:] if r.data.get("weight_kg") is not None), None)

    def delta(field: str) -> float | None:
        current = data.get(field)
        if current is None:
            return None
        candidates = [r for r in rows[1:] if r.data.get(field) is not None]
        if not candidates:
            return None
        anchor = min(candidates, key=lambda r: abs((r.recorded_at - target).total_seconds()))
        if abs((anchor.recorded_at - target).total_seconds()) > 10 * 86400:
            return None
        return round(float(current) - float(anchor.data[field]), 1)

    spark = [r for r in rows if r.data.get("weight_kg") is not None][:8]
    return {
        "weightKg": data["weight_kg"],
        "weightDelta30d": delta("weight_kg"),
        "weightDeltaPrev": round(float(data["weight_kg"]) - float(previous.data["weight_kg"]), 1)
        if previous
        else None,
        "ageDaysLabel": _age_label(age),
        "source": latest.source or "",
        "sparkWeights": [r.data["weight_kg"] for r in reversed(spark)],
        "fatPct": data.get("body_fat_pct"),
        "fatPctDelta30d": delta("body_fat_pct"),
        "muscleKg": data.get("muscle_kg"),
        "muscleKgDelta30d": delta("muscle_kg"),
        "leanKg": data.get("lean_mass_kg"),
        "leanKgDelta30d": delta("lean_mass_kg"),
    }


async def card(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=["body_composition"], limit=12
    )
    out = empty_card()
    block = featured(rows, ctx)
    out["featured"] = block
    if block:
        pills = []
        if (d := block.get("weightDelta30d")) is not None:
            pills.append(f"{'+' if d > 0 else ''}{d}kg 30d")  # type: ignore[operator]
        if (fat := block.get("fatPct")) is not None:
            pills.append(f"Fat {fat}%")
        out["tile"] = {
            "agent": "body",
            "label": "Body",
            "metric": f"{block['weightKg']} kg",
            "tint": "neutral",
            "detail": " · ".join(pills) if pills else None,
            "progress": None,
        }
    return out
