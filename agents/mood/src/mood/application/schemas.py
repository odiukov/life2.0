from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_TAGS = 6


class MoodExtraction(BaseModel):
    mood_score: int | None = Field(
        default=None, ge=1, le=10, description="General 'how am I' score"
    )
    energy: int | None = Field(default=None, ge=1, le=10, description="Energy; low when tired")
    stress: int | None = Field(default=None, ge=1, le=10, description="Stress or anxiety")
    valence: Literal["pos", "neu", "neg"] | None = None
    tags: list[str] = Field(
        default_factory=list, description="Short lowercase descriptors, at most 6"
    )
    summary: str = Field(description="One-line paraphrase, or 'no mood signal'")

    @field_validator("tags")
    @classmethod
    def _tags(cls, value: list[str]) -> list[str]:
        cleaned = [t.strip().lower() for t in value if isinstance(t, str) and t.strip()]
        return cleaned[:MAX_TAGS]
