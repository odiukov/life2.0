from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from shared.analysis.matching import slug


class MedicationDefinition(BaseModel):
    name: str = Field(
        description="lowercase kebab-case English name (translate other languages): vitamin-d, b12, ibuprofen"
    )
    dose: str | None = Field(default=None, description="as stated, e.g. 2000 IU, 500 mg")
    schedule: str = Field(description="free text, e.g. 'daily 21:00', 'mon,wed,fri morning'")
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        normalized = slug(value)
        if not normalized:
            raise ValueError("name must contain latin letters or digits")
        return normalized

    @field_validator("schedule")
    @classmethod
    def _schedule(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("schedule is required")
        return value.strip()
