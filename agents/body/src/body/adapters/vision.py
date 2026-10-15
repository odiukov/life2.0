from __future__ import annotations

import base64
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage
from shared.adapters.llm.json_extract import extract_json
from shared.ports.chat_model import ChatModelFactory
from shared.ports.llm import LLMTask

from body.application.ports import VisionUnavailable

METRICS_PROMPT = """\
This is a ViHealth body composition report.

Extract the following (use null if not visible):
{
  "weight_kg": number (Body composition table, Weight row, first measurement value e.g. 79.6),
  "body_fat_kg": number (Body fat row, first measurement value),
  "body_fat_pct": number (Body fat rate gauge value, e.g. 26.5),
  "bone_mass_kg": number (Bone mass row, first measurement value),
  "protein_kg": number (Protein row, first measurement value),
  "body_water_kg": number (Body water row, first measurement value),
  "muscle_kg": number (Muscle row, first measurement value),
  "skeletal_muscle_kg": number (Skeletal muscle row, first measurement value),
  "bmi": number (BMI gauge value),
  "body_score": number (Body score panel, value out of 100),
  "visceral_fat_grade": number (Other indicators: Visceral fat grade),
  "bmr_kcal": number (Other indicators: Basal metabolic rate, digits only),
  "fat_free_kg": number (Other indicators: Fat-free body weight, digits only),
  "subcutaneous_fat_pct": number (Other indicators: Subcutaneous fat, digits only),
  "body_age": number (Other indicators: Body age),
  "recorded_at": "YYYY-MM-DDTHH:MM:SS" (Measuring time panel)
}

Return ONLY valid JSON, no explanation."""
PROFILE_PROMPT = """\
This is a ViHealth body composition report from LePulse smart scales.

Extract the following from the report (use null if not visible):
{
  "weight_kg": number (Weight row, first number only — e.g. from "79.6(54.1-73.1)" use 79.6),
  "height_cm": number (from the Name/Gender/Age/Height info panel),
  "age": number (age in years from the info panel),
  "sex": "male" or "female" (gender from the info panel)
}

Return ONLY valid JSON, no explanation."""
FLOAT_KEYS = (
    "weight_kg",
    "body_fat_kg",
    "body_fat_pct",
    "bone_mass_kg",
    "protein_kg",
    "body_water_kg",
    "muscle_kg",
    "skeletal_muscle_kg",
    "bmi",
    "body_score",
    "visceral_fat_grade",
    "bmr_kcal",
    "fat_free_kg",
    "subcutaneous_fat_pct",
    "body_age",
)
TIME_FORMATS = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d %b %Y, %H:%M:%S", "%d %b %Y %H:%M:%S")


class ChatModelVision:
    def __init__(self, chat_models: ChatModelFactory) -> None:
        self._chat_models = chat_models

    async def _ask(self, png: bytes, prompt: str) -> dict[str, object]:
        image = "data:image/png;base64," + base64.standard_b64encode(png).decode()
        message = HumanMessage(
            content=[
                {"type": "image_url", "image_url": {"url": image}},
                {"type": "text", "text": prompt},
            ]
        )
        try:
            response = await self._chat_models.chat_model(LLMTask.VISION).ainvoke([message])
        except Exception as exc:  # providers raise their own error types
            raise VisionUnavailable(type(exc).__name__) from None
        content = response.content
        if isinstance(content, list):
            content = "".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        try:
            parsed = extract_json(str(content))
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    async def metrics(self, png: bytes) -> tuple[datetime | None, dict[str, float]]:
        raw = await self._ask(png, METRICS_PROMPT)
        metrics: dict[str, float] = {}
        for key in FLOAT_KEYS:
            try:
                if raw.get(key) is not None:
                    metrics[key] = float(raw[key])  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        when = None
        for fmt in TIME_FORMATS:
            try:
                when = datetime.strptime(str(raw.get("recorded_at") or "").strip(), fmt).replace(
                    tzinfo=UTC
                )
                break
            except ValueError:
                continue
        return when, metrics

    async def profile(self, png: bytes) -> dict[str, object]:
        raw = await self._ask(png, PROFILE_PROMPT)
        out: dict[str, object] = {}
        for key, cast in (("weight_kg", float), ("height_cm", float), ("age", int)):
            try:
                if raw.get(key) is not None:
                    out[key] = cast(raw[key])  # type: ignore[arg-type, call-overload]
            except (TypeError, ValueError):
                continue
        sex = str(raw.get("sex") or "").lower()
        if sex in ("male", "female"):
            out["sex"] = sex
        return out
