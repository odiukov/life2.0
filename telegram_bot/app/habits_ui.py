"""Inline keyboard builder and callback handler for /habits."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from shared.db import fetch_active_habits, fetch_habit_logs

from .client import habits_a2a_call

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("Europe/Kyiv")
_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _done_today(habit: dict, logs_today: list[dict]) -> bool:
    if not logs_today:
        return False
    if habit["kind"] == "boolean":
        return any(d.get("completed") for d in logs_today)
    total = 0.0
    for d in logs_today:
        try:
            total += float(d.get("value") or 0)
        except (TypeError, ValueError):
            continue
    target = habit.get("target_value") or 0
    return total >= float(target) if target > 0 else total > 0


def _streak(habit: dict, logs: list[dict], today_local: datetime) -> int:
    by_day: dict[str, list[dict]] = {}
    for r in logs:
        d_local = r["recorded_at"].astimezone(_TZ).date().isoformat()
        by_day.setdefault(d_local, []).append(r.get("data") or {})
    streak = 0
    cursor = today_local
    for _ in range(400):
        key = cursor.date().isoformat()
        if habit["cadence_type"] == "weekly":
            if _WEEKDAYS[cursor.weekday()] not in (habit.get("cadence_days") or []):
                cursor -= timedelta(days=1)
                continue
        if _done_today(habit, by_day.get(key, [])):
            streak += 1
            cursor -= timedelta(days=1)
        else:
            break
    return streak


async def build_habits_keyboard() -> tuple[InlineKeyboardMarkup | None, str]:
    habits = await fetch_active_habits()
    if not habits:
        return None, "no habits yet — `/habit new ...` to create one"
    logs = await fetch_habit_logs(days=180)
    logs_by_habit: dict[str, list[dict]] = {}
    for r in logs:
        hid = (r.get("data") or {}).get("habit_id")
        if hid:
            logs_by_habit.setdefault(hid, []).append(r)
    today = datetime.now(_TZ)
    today_key = today.date().isoformat()
    rows = []
    for h in habits:
        h_logs = logs_by_habit.get(h["id"], [])
        today_logs = [r.get("data") or {} for r in h_logs
                      if r["recorded_at"].astimezone(_TZ).date().isoformat() == today_key]
        done = _done_today(h, today_logs)
        streak = _streak(h, h_logs, today)
        marker = "✅" if done else "⬜"
        label = f"{marker} {h['name']} ({streak}d)"
        rows.append([InlineKeyboardButton(label, callback_data=f"h:{h['id']}")])
    return InlineKeyboardMarkup(rows), ""


async def on_habit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if not data.startswith("h:"):
        return
    habit_id = data[2:]
    try:
        await habits_a2a_call(
            skill="log_habit_check",
            message="/habit (button)",
            params={"habit_id": habit_id, "source": "telegram"},
        )
    except Exception as e:
        logger.warning("habit callback failed: %s", e)
        await query.edit_message_text("failed to log — try again")
        return
    markup, empty = await build_habits_keyboard()
    if markup is None:
        await query.edit_message_text(empty)
    else:
        await query.edit_message_reply_markup(reply_markup=markup)
