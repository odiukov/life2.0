from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from shared.analysis.matching import slug

from habits.domain.habit import WEEKDAYS


class HabitDefinition(BaseModel):
    name: str = Field(
        description="lowercase kebab-case English name, e.g. meditation, cold-shower, no-alcohol; "
        "translate names given in other languages"
    )
    kind: Literal["boolean", "quantitative"]
    cadence_type: Literal["daily", "weekly"]
    cadence_days: list[str] | None = Field(
        default=None, description="mon..sun, required for weekly"
    )
    target_value: float | None = Field(default=None, gt=0, description="only for quantitative")
    unit: str | None = Field(default=None, description="only for quantitative, e.g. min, pages, km")

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        normalized = slug(value)
        if not normalized:
            raise ValueError("empty habit name")
        return normalized

    @model_validator(mode="after")
    def _rules(self) -> HabitDefinition:
        if self.cadence_type == "weekly":
            days = [
                d.strip().lower()[:3]
                for d in (self.cadence_days or [])
                if d.strip().lower()[:3] in WEEKDAYS
            ]
            if not days:
                raise ValueError("weekly habits need cadence_days")
            self.cadence_days = list(dict.fromkeys(days))
        else:
            self.cadence_days = None
        if self.kind == "boolean":
            self.target_value, self.unit = None, None
        return self
