# orchestrator/app/briefing.py
import asyncio
import logging
import os

import httpx

from shared.claude_runner import run_claude

logger = logging.getLogger(__name__)


def _fmt_duration(seconds: int) -> str:
    """Format seconds as 'Xh Ym' (e.g. '7h 23m')."""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"


def format_message(metrics: dict, insight: str | None) -> str:
    """Assemble the final Telegram briefing message from metrics and optional insight."""
    lines = [
        "🌅 Good morning! Here's your health brief.",
        "",
        f"📊 Yesterday — {metrics['date']}",
    ]

    sleep = metrics.get("sleep")
    if sleep:
        dur = _fmt_duration(sleep["duration_seconds"])
        deep = _fmt_duration(sleep["deep_sleep_seconds"])
        hrv_part = f" · HRV {sleep['hrv']} ms" if sleep.get("hrv") else ""
        lines.append(f"• Sleep: {dur} · Deep {deep}{hrv_part}")

    workout = metrics.get("workout")
    if workout:
        dist_km = workout["total_distance_meters"] / 1000
        name = workout["first_name"] or workout["first_type"] or "Workout"
        kcal = workout["total_calories"]
        count = workout["activity_count"]
        count_part = f" +{count - 1} more" if count > 1 else ""
        lines.append(f"• Workout: {name}{count_part} {dist_km:.1f} km · {kcal:,} kcal burned")

    nutrition = metrics.get("nutrition")
    if nutrition:
        lines.append(
            f"• Nutrition: {nutrition['kcal']:,} kcal · "
            f"Protein {nutrition['protein_g']}g · "
            f"Carbs {nutrition['carbs_g']}g · "
            f"Fat {nutrition['fat_g']}g"
        )

    if insight:
        lines.append("")
        lines.append(f"💡 {insight}")

    return "\n".join(lines)
