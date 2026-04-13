# Workout + Nutrition Agents — Design Spec
_Date: 2026-04-13_

## Overview

Plan 2 adds two new agents — `agent-workout` (port 8002) and `agent-nutrition` (port 8003) — following the same FastAPI + A2A pattern as `agent-sleep`. Both agents share cross-domain context by reading each other's `health_logs` rows directly from Postgres (no inter-agent HTTP calls).

---

## 1. Agent Structure

Both agents follow the identical layout as `agents/sleep/`:

```
agents/workout/
  Dockerfile
  requirements.txt
  app/
    __init__.py
    main.py          # FastAPI: /tasks, /.well-known/agent.json, /health
    agent_card.py    # A2A card with capabilities
    tasks.py         # handle_task → claude_runner + insert_task + upsert_memory
    prompt.py        # build_workout_prompt

agents/nutrition/
  Dockerfile
  requirements.txt
  app/
    __init__.py
    main.py
    agent_card.py
    tasks.py
    prompt.py        # build_nutrition_prompt
```

---

## 2. Capabilities

### Workout Agent

| Task | Description |
|---|---|
| `log_workout` | Record a completed workout session |
| `analyze_workout` | Analyze training load, progress, recovery |
| `get_recommendations` | Suggest next workout based on history and nutrition |

### Nutrition Agent

| Task | Description |
|---|---|
| `log_meal` | Log a meal from free text; Claude parses КБЖУ |
| `analyze_nutrition` | Analyze caloric intake, macro balance, trends |
| `get_recommendations` | Suggest nutrition adjustments based on recent workouts |

---

## 3. Data Schema

All data stored in existing `health_logs` table (`agent`, `type`, `data` JSONB, `recorded_at`, `source`).

### Workout `data` shapes

**Strength:**
```json
{
  "type": "strength",
  "exercises": [
    { "name": "bench press", "sets": 4, "reps": 10, "weight_kg": 80 }
  ],
  "duration_min": 60,
  "feeling": "good"
}
```

**Cycling:**
```json
{
  "type": "cycling",
  "distance_km": 35,
  "duration_min": 80,
  "avg_hr": 145,
  "feeling": "hard"
}
```

**Combat (boxing / MMA / Muay Thai):**
```json
{
  "type": "combat",
  "discipline": "muay_thai",
  "duration_min": 90,
  "intensity": "high",
  "feeling": "great"
}
```

### Nutrition `data` shape

```json
{
  "raw_text": "гречка с курицей и салат",
  "meal_type": "lunch",
  "parsed": {
    "kcal": 520,
    "protein_g": 42,
    "carbs_g": 55,
    "fat_g": 10
  }
}
```

`parsed` is filled by Claude from `raw_text`. May be `null` if Claude is uncertain — agent states this explicitly in the response.

---

## 4. Cross-Agent Context (Shared DB approach)

Agents read each other's logs directly from Postgres when building their prompts. No HTTP calls between agents.

### Workout prompt context
1. Last 10 rows from `health_logs WHERE agent = 'workout'`
2. Last 5 rows from `health_logs WHERE agent = 'nutrition'`
3. Semantic search in `workout_memories` Qdrant collection (top 5)

### Nutrition prompt context
1. Last 10 rows from `health_logs WHERE agent = 'nutrition'`
2. Last 3 rows from `health_logs WHERE agent = 'workout'`
3. Semantic search in `nutrition_memories` Qdrant collection (top 5)

This allows the workout agent to notice low protein intake on training days, and the nutrition agent to recommend higher caloric intake after intense sessions.

---

## 5. Orchestrator Changes

Minimal changes required — almost everything is already in place.

### `.env` — extend `AGENT_URLS`:
```
AGENT_URLS=http://agent-sleep:8001,http://agent-workout:8002,http://agent-nutrition:8003
```

Discovery is automatic: on startup the orchestrator queries `/.well-known/agent.json` on each URL and registers the agent by name.

### No code changes needed:
- `classify_intent()` — workout and nutrition keywords already defined in `router.py`
- `AGENT_DEFAULT_TASK` — already has `"workout": "analyze_workout"` and `"nutrition": "analyze_nutrition"` in `orchestrator/app/main.py`

---

## 6. Docker Compose

Two new services added to `docker-compose.yml`:

```yaml
agent-workout:
  build:
    context: .
    dockerfile: agents/workout/Dockerfile
  ports:
    - "8002:8002"
  env_file:
    - .env
    - .env.auth
  volumes:
    - ~/.claude:/root/.claude:ro
  depends_on:
    postgres:
      condition: service_healthy
    qdrant:
      condition: service_healthy

agent-nutrition:
  build:
    context: .
    dockerfile: agents/nutrition/Dockerfile
  ports:
    - "8003:8003"
  env_file:
    - .env
    - .env.auth
  volumes:
    - ~/.claude:/root/.claude:ro
  depends_on:
    postgres:
      condition: service_healthy
    qdrant:
      condition: service_healthy
```

---

## 7. Qdrant Collections

`workout_memories` and `nutrition_memories` are created automatically on first `upsert_memory()` call — same behaviour as `sleep_memories`. No manual collection setup needed.

---

## 8. Testing

Follow the pattern from `tests/test_sleep_tasks.py`:

- `test_workout_tasks.py` — mock `run_claude`, `insert_task`, `upsert_memory`; verify all three task types return `{"status": "completed"}`
- `test_nutrition_tasks.py` — same pattern; additionally verify `log_meal` stores `raw_text` in params
- `test_agent_card.py` — extend to cover workout and nutrition agent cards (capabilities list)
