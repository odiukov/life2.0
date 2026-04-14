# orchestrator/app/briefing.py
import asyncio
import logging
import os

import httpx

from shared.claude_runner import run_claude
from .db import get_yesterday_metrics

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


def _agent_params(agent_name: str, metrics: dict) -> dict | None:
    """Build params dict for a briefing task call to a specific agent.
    Returns None if that domain has no data (skip the call)."""
    domain_metrics = metrics.get(agent_name)
    if domain_metrics is None:
        return None
    return dict(domain_metrics)


def _extract_briefing_text(data: dict) -> str:
    """Extract text from agent briefing response."""
    artifacts = data.get("artifacts", [])
    if artifacts and artifacts[0].get("parts"):
        return artifacts[0]["parts"][0].get("text", "")
    return data.get("output", "")


async def call_agents_for_briefing(agents: dict, metrics: dict) -> dict[str, str]:
    """Call sleep/workout/nutrition agents in parallel with briefing task.

    Skips agents whose domain metrics are None.
    Returns dict mapping agent name → domain summary text.
    """
    domain_names = ["sleep", "workout", "nutrition"]
    tasks_to_run: list[tuple[str, str, dict]] = []  # (name, url, params)

    for name in domain_names:
        agent_entry = agents.get(name)
        if not agent_entry:
            continue
        params = _agent_params(name, metrics)
        if params is None:
            continue
        tasks_to_run.append((name, agent_entry["url"], params))

    if not tasks_to_run:
        return {}

    async def _call_one(name: str, url: str, params: dict) -> tuple[str, str]:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{url}/tasks",
                    json={"id": "", "task": "briefing", "params": params},
                )
                resp.raise_for_status()
                return name, _extract_briefing_text(resp.json())
        except Exception as e:
            logger.warning("Briefing agent call failed for %s: %s", name, e)
            return name, ""

    results = await asyncio.gather(*[_call_one(n, u, p) for n, u, p in tasks_to_run])
    return {name: text for name, text in results if text}


def generate_insight(metrics: dict, summaries: dict[str, str]) -> str:
    """Generate a 1-2 sentence cross-domain insight via Claude.

    metrics: output of get_yesterday_metrics()
    summaries: agent briefing summaries keyed by domain name
    """
    domain_sections = "\n".join(
        f"## {name.capitalize()} summary:\n{text}"
        for name, text in summaries.items()
    )
    prompt = f"""You are a personal health coach reviewing yesterday's health data.

{domain_sections}

Write a single 1-2 sentence plain-text insight (no markdown, no bullet points) that connects patterns across sleep, workout, and nutrition.
Focus on the most actionable cross-domain observation for today."""
    return run_claude(prompt, timeout=60)


async def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    """Send a message via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json={"chat_id": chat_id, "text": text})
        resp.raise_for_status()


async def run_briefing(agents: dict, use_today: bool = False) -> dict:
    """Top-level briefing orchestrator.

    agents: registry dict from get_registry() — {name: {url, card}}
    Returns {"status": "sent" | "skipped" | "error", "reason": str}
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        logger.warning("Briefing Telegram send skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return {"status": "skipped", "reason": "telegram not configured"}

    try:
        metrics = await get_yesterday_metrics(use_today=use_today)
    except Exception as e:
        logger.error("Briefing DB query failed: %s", e)
        return {"status": "error", "reason": f"db error: {e}"}
    has_any = any(metrics.get(d) for d in ["sleep", "workout", "nutrition"])
    if not has_any:
        logger.warning("Briefing skipped: no health data for yesterday")
        return {"status": "skipped", "reason": "no data for yesterday"}

    summaries = await call_agents_for_briefing(agents, metrics)

    insight = None
    if summaries:
        try:
            insight = await asyncio.to_thread(generate_insight, metrics, summaries)
        except Exception as e:
            logger.warning("Briefing insight generation failed: %s — sending metrics only", e)

    message = format_message(metrics, insight)

    try:
        await send_telegram_message(bot_token, chat_id, message)
        logger.info("Daily briefing sent to Telegram")
        return {"status": "sent"}
    except Exception as e:
        logger.error("Briefing Telegram send failed: %s", e)
        return {"status": "error", "reason": str(e)}
