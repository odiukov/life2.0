#!/usr/bin/env python3
"""Seed a demo user with synthetic health data.

Useful for screenshots, demos, and poking at the UI without connecting any real
integration. Every value is generated — nothing here comes from a real person.

    python scripts/seed_demo_data.py                 # 21 days, default demo user
    python scripts/seed_demo_data.py --days 45
    python scripts/seed_demo_data.py --reset         # wipe the demo user first

Requires the stack to be up (`docker compose up -d`); talks to Postgres on
localhost:5432 using the credentials from .env.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parent.parent

DEMO_USER_ID = "de000000-0000-4000-8000-000000000001"
DEMO_USER_NAME = "Demo"
DEMO_TIMEZONE = "Europe/Kyiv"

WORKOUTS = [
    ("Morning Run", "running", 5200, 2100, 430, 152, 176),
    ("Evening Run", "running", 8100, 2900, 640, 148, 171),
    ("Gym — Upper Body", "strength_training", 0, 3300, 380, 118, 149),
    ("Gym — Legs", "strength_training", 0, 3600, 420, 122, 155),
    ("Pool", "lap_swimming", 1500, 2400, 460, 131, 158),
    ("City Walk", "walking", 4400, 2900, 290, 106, 128),
    ("Indoor Cycling", "cycling", 21000, 3000, 540, 139, 168),
]

MEALS = {
    "breakfast": [
        ("Oatmeal with banana and peanut butter", 470, 24, 58, 16),
        ("Scrambled eggs, rye toast, avocado", 520, 28, 34, 30),
        ("Greek yoghurt, granola, blueberries", 390, 22, 47, 11),
    ],
    "lunch": [
        ("Chicken breast, rice, roasted vegetables", 680, 52, 71, 16),
        ("Salmon poke bowl", 720, 41, 66, 30),
        ("Lentil soup and wholegrain bread", 540, 26, 74, 13),
    ],
    "dinner": [
        ("Beef stir-fry with noodles", 780, 46, 79, 27),
        ("Cottage cheese, tomatoes, olive oil", 430, 39, 14, 24),
        ("Turkey meatballs and mashed potato", 640, 44, 58, 24),
    ],
    "snack": [
        ("Protein shake", 220, 30, 12, 4),
        ("Apple and almonds", 260, 7, 24, 16),
        ("Dark chocolate", 180, 2, 18, 11),
    ],
}

MOOD_TAGS = [
    ["focused", "calm"],
    ["tired", "stressed"],
    ["energised", "social"],
    ["flat", "restless"],
    ["content"],
]

# (id, name, kind, cadence_type, cadence_days, target_value, unit)
HABITS = [
    ("a1000000-0000-4000-8000-000000000001", "Morning walk", "boolean", "daily", None, None, None),
    ("a1000000-0000-4000-8000-000000000002", "Read 20 pages", "boolean", "daily", None, None, None),
    ("a1000000-0000-4000-8000-000000000003", "Water", "quantitative", "daily", None, 2.5, "L"),
    ("a1000000-0000-4000-8000-000000000004", "Strength training", "boolean", "weekly",
     ["tue", "thu", "sat"], None, None),
]

MEDICATIONS = [
    ("Vitamin D", "2000 IU", "daily, morning"),
    ("Magnesium", "300 mg", "daily, evening"),
    ("Omega-3", "1000 mg", "daily, with lunch"),
]


def load_env() -> dict[str, str]:
    env_path = REPO_ROOT / ".env"
    values: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip()
    return values


def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def jsonb(payload: dict) -> str:
    return f"'{sql_escape(json.dumps(payload, ensure_ascii=False))}'::jsonb"


def ts(moment: datetime) -> str:
    return f"'{moment.astimezone(timezone.utc).isoformat()}'::timestamptz"


def local(day: date, hour: int, minute: int = 0) -> datetime:
    """A wall-clock moment on `day` in the demo user's timezone."""
    return datetime.combine(day, time(hour=hour, minute=minute), tzinfo=ZoneInfo(DEMO_TIMEZONE))


def health_log(agent: str, type_: str, source: str, recorded_at: datetime, data: dict) -> str:
    return (
        "INSERT INTO health_logs (user_id, agent, type, source, recorded_at, data) VALUES "
        f"('{DEMO_USER_ID}', '{agent}', '{type_}', '{source}', {ts(recorded_at)}, {jsonb(data)}) "
        "ON CONFLICT DO NOTHING;"
    )


def build_statements(days: int, rng: random.Random) -> list[str]:
    out: list[str] = [
        "INSERT INTO users (id, name, timezone, preferences) VALUES "
        f"('{DEMO_USER_ID}', '{DEMO_USER_NAME}', '{DEMO_TIMEZONE}', "
        "'{\"locale\": \"en\"}'::jsonb) ON CONFLICT (id) DO NOTHING;"
    ]

    today = date.today()
    weight = 78.4

    for offset in range(days, -1, -1):
        day = today - timedelta(days=offset)
        # Slow downward weight trend with day-to-day noise.
        weight += rng.uniform(-0.35, 0.28) - 0.012
        # All local times are in the demo user's timezone so that day-boundary
        # aggregation in the orchestrator lines up with what the screens show.
        wake = local(day, 7)

        # ── Sleep ──────────────────────────────────────────────────────────
        duration = int(rng.gauss(7.4 * 3600, 40 * 60))
        duration = max(4 * 3600, min(duration, 9 * 3600 + 1800))
        deep = int(duration * rng.uniform(0.11, 0.19))
        rem = int(duration * rng.uniform(0.18, 0.26))
        awake = int(rng.uniform(600, 2400))
        light = max(0, duration - deep - rem - awake)
        score = max(40, min(96, int(50 + duration / 3600 * 5 + rng.uniform(-8, 8))))
        bedtime = wake - timedelta(seconds=duration + awake)
        out.append(
            health_log(
                "sleep", "sleep_session", "garmin", wake,
                {
                    "score": score,
                    "avg_hr": round(rng.uniform(54, 66), 1),
                    "start_time": bedtime.replace(tzinfo=None).isoformat(),
                    "end_time": wake.replace(tzinfo=None).isoformat(),
                    "duration_seconds": duration,
                    "deep_sleep_seconds": deep,
                    "rem_sleep_seconds": rem,
                    "light_sleep_seconds": light,
                    "awake_seconds": awake,
                    "hrv_weekly_avg": None,
                },
            )
        )

        rmssd = int(rng.gauss(43, 6))
        out.append(
            health_log(
                "sleep", "hrv_status", "garmin", wake + timedelta(minutes=5),
                {
                    "hrv_rmssd": rmssd,
                    "status": "BALANCED" if 34 <= rmssd <= 52 else "UNBALANCED",
                    "baseline_low": 34,
                    "baseline_high": 52,
                },
            )
        )

        steps = int(rng.gauss(8600, 2600))
        out.append(
            health_log(
                "sleep", "daily_stats", "garmin", local(day, 22),
                {
                    "steps": max(1200, steps),
                    "resting_hr": int(rng.gauss(58, 3)),
                    "stress_avg": int(rng.gauss(31, 7)),
                    "calories_active": round(rng.uniform(280, 780), 1),
                    "body_battery_max": int(rng.uniform(72, 96)),
                    "body_battery_min": int(rng.uniform(12, 34)),
                },
            )
        )

        # ── Workout: roughly four sessions a week ──────────────────────────
        if rng.random() < 0.58:
            name, kind, dist, secs, kcal, avg_hr, max_hr = rng.choice(WORKOUTS)
            jitter = rng.uniform(0.85, 1.15)
            out.append(
                health_log(
                    "workout", "activity", "garmin", local(day, rng.choice([7, 12, 18, 19, 20]), rng.randint(0, 55)),
                    {
                        "name": name,
                        "activity_type": kind,
                        "distance_meters": int(dist * jitter),
                        "duration_seconds": int(secs * jitter),
                        "calories": round(kcal * jitter),
                        "avg_hr": round(avg_hr * rng.uniform(0.96, 1.04), 1),
                        "max_hr": round(max_hr * rng.uniform(0.97, 1.03), 1),
                    },
                )
            )

        # ── Nutrition ──────────────────────────────────────────────────────
        for meal_type, hour in (("breakfast", 8), ("lunch", 13), ("dinner", 19), ("snack", 16)):
            if meal_type == "snack" and rng.random() < 0.4:
                continue
            label, kcal, protein, carbs, fat = rng.choice(MEALS[meal_type])
            jitter = rng.uniform(0.9, 1.1)
            totals = {
                "kcal": round(kcal * jitter, 1),
                "protein_g": round(protein * jitter, 1),
                "carbs_g": round(carbs * jitter, 1),
                "fat_g": round(fat * jitter, 1),
            }
            out.append(
                health_log(
                    "nutrition", "meal", "yazio",
                    local(day, hour, rng.randint(0, 50)),
                    {
                        "date": day.isoformat(),
                        "meal_type": meal_type,
                        "items": [{"name": label, "amount_g": 1, **totals}],
                        "totals": totals,
                    },
                )
            )

        # ── Body composition, every other day ──────────────────────────────
        if offset % 2 == 0:
            fat_pct = round(rng.gauss(21.5, 0.6), 1)
            fat_kg = round(weight * fat_pct / 100, 1)
            lean = round(weight - fat_kg, 1)
            out.append(
                health_log(
                    "body", "body_composition", "manual", local(day, 7, 25),
                    {
                        "weight_kg": round(weight, 1),
                        "bmi": round(weight / (1.79 ** 2), 1),
                        "body_fat_pct": fat_pct,
                        "body_fat_kg": fat_kg,
                        "lean_mass_kg": lean,
                        "fat_free_kg": lean,
                        "muscle_kg": round(lean * 0.93, 1),
                        "skeletal_muscle_kg": round(lean * 0.56, 1),
                        "body_water_kg": round(lean * 0.73, 1),
                        "bone_mass_kg": 3.9,
                        "protein_kg": round(lean * 0.2, 1),
                        "bmr_kcal": round(370 + 21.6 * lean),
                        "visceral_fat_grade": 5.0,
                        "body_score": int(rng.uniform(74, 86)),
                        "body_age": 29.0,
                    },
                )
            )

        # ── Mood ───────────────────────────────────────────────────────────
        # Always log the two most recent days so the dashboard has something to show.
        if offset <= 1 or rng.random() < 0.85:
            tags = rng.choice(MOOD_TAGS)
            mood_score = max(3, min(9, int(rng.gauss(7.0, 1.1))))
            out.append(
                health_log(
                    "mood", "mood", "manual", local(day, 21, rng.randint(0, 45)),
                    {
                        "mood_score": mood_score,
                        "energy": max(1, min(10, mood_score + rng.randint(-2, 2))),
                        "stress": max(1, min(10, 10 - mood_score + rng.randint(-1, 2))),
                        "valence": "positive" if mood_score >= 6 else "negative",
                        "tags": tags,
                        "raw_text": f"Feeling {tags[0]} today.",
                        "source_skill": "log_mood",
                    },
                )
            )

        # ── Habits ─────────────────────────────────────────────────────────
        weekday = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][(day.toordinal() - 1) % 7]
        for habit_id, habit_name, kind, cadence, cadence_days, target, unit in HABITS:
            if cadence == "weekly" and weekday not in (cadence_days or []):
                continue
            if rng.random() > 0.85:
                continue
            data: dict = {"habit_id": habit_id, "habit_name": habit_name, "completed": True}
            if kind == "quantitative":
                data["value"] = round(rng.uniform(2.4, 3.2), 1)
                data["unit"] = unit
            out.append(
                health_log("habits", "habit", "manual", local(day, 20, rng.randint(0, 45)), data)
            )

        # ── Medication ─────────────────────────────────────────────────────
        for med_name, dose, _schedule in MEDICATIONS:
            if rng.random() > 0.85:
                continue
            out.append(
                health_log(
                    "medication", "medication_taken", "manual",
                    local(day, 9, rng.randint(0, 40)),
                    {"name": med_name, "dose_at_time": dose, "source_skill": "log_medication"},
                )
            )

    for habit_id, name, kind, cadence, cadence_days, target, unit in HABITS:
        target_sql = "NULL" if target is None else str(target)
        unit_sql = "NULL" if unit is None else f"'{sql_escape(unit)}'"
        days_sql = (
            "NULL" if not cadence_days
            else "ARRAY[" + ", ".join(f"'{d}'" for d in cadence_days) + "]::text[]"
        )
        out.append(
            "INSERT INTO habits (id, user_id, name, kind, cadence_type, cadence_days, target_value, unit) "
            f"VALUES ('{habit_id}', '{DEMO_USER_ID}', '{sql_escape(name)}', '{kind}', '{cadence}', "
            f"{days_sql}, {target_sql}, {unit_sql}) ON CONFLICT DO NOTHING;"
        )

    for name, dose, schedule in MEDICATIONS:
        out.append(
            "INSERT INTO medications (user_id, name, dose, schedule) VALUES "
            f"('{DEMO_USER_ID}', '{sql_escape(name)}', '{sql_escape(dose)}', '{sql_escape(schedule)}') "
            "ON CONFLICT DO NOTHING;"
        )

    return out


def reset_statements() -> list[str]:
    return [
        f"DELETE FROM health_logs WHERE user_id = '{DEMO_USER_ID}';",
        f"DELETE FROM habits WHERE user_id = '{DEMO_USER_ID}';",
        f"DELETE FROM medications WHERE user_id = '{DEMO_USER_ID}';",
    ]


def run_sql(sql: str, env: dict[str, str]) -> None:
    user = env.get("POSTGRES_USER", "lifeagents")
    db = env.get("POSTGRES_DB", "lifeagents")
    proc = subprocess.run(
        ["docker", "compose", "exec", "-T", "postgres", "psql", "-U", user, "-d", db, "-v", "ON_ERROR_STOP=1", "-q"],
        cwd=REPO_ROOT,
        input=sql,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"psql failed with code {proc.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=21, help="How many days of history to generate")
    parser.add_argument("--seed", type=int, default=20260828, help="RNG seed, for reproducible data")
    parser.add_argument("--reset", action="store_true", help="Delete existing demo rows first")
    parser.add_argument("--print-only", action="store_true", help="Print SQL instead of executing it")
    args = parser.parse_args()

    env = load_env()
    rng = random.Random(args.seed)

    statements: list[str] = []
    if args.reset:
        statements += reset_statements()
    statements += build_statements(args.days, rng)
    sql = "\n".join(statements)

    if args.print_only:
        print(sql)
        return

    run_sql(sql, env)
    print(f"Seeded demo user {DEMO_USER_ID} with {args.days} days of synthetic data.")
    print(f"Point the app at it with:  X-User-Id: {DEMO_USER_ID}  (AUTH_MODE=dev)")


if __name__ == "__main__":
    main()
