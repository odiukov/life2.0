"""What the LLM returns for a kitchen message, using flat operation lists."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator

from kitchen.domain.model import Category, Location
from kitchen.domain.units import InputUnit


class AddItem(BaseModel):
    name: str = Field(min_length=1, description="Normalized product name, lowercase, nominative.")
    display_name: str = Field(description="Name with useful details from the message.")
    quantity: float = Field(gt=0, allow_inf_nan=False)
    unit: InputUnit
    location: Location
    category: Category
    opened: bool = False
    expires_on: date | None = None
    shelf_life_days: int | None = Field(default=None, ge=0, le=3650)
    opened_shelf_life_days: int | None = Field(default=None, ge=0, le=3650)

    @model_validator(mode="after")
    def _needs_expiry(self) -> AddItem:
        if self.expires_on is None and self.shelf_life_days is None:
            raise ValueError("either expires_on or shelf_life_days is required")
        return self


class ConsumeItem(BaseModel):
    item_ref: str = Field(min_length=1, description="Inventory name of the consumed product.")
    quantity: float | None = Field(
        default=None, gt=0, allow_inf_nan=False, description="Omit when all was used."
    )
    unit: InputUnit | None = None


class DiscardItem(BaseModel):
    item_ref: str = Field(min_length=1)
    reason: str | None = None


class UpdateItem(BaseModel):
    item_ref: str = Field(min_length=1)
    opened: bool | None = None
    location: Location | None = None
    expires_on: date | None = None
    opened_shelf_life_days: int | None = Field(default=None, ge=0, le=3650)


class QueryInventory(BaseModel):
    question: str = Field(min_length=1)


class OperationList(BaseModel):
    adds: list[AddItem] = Field(default_factory=list)
    consumes: list[ConsumeItem] = Field(default_factory=list)
    discards: list[DiscardItem] = Field(default_factory=list)
    updates: list[UpdateItem] = Field(default_factory=list)
    queries: list[QueryInventory] = Field(default_factory=list)

    undo_last: bool = Field(
        default=False, description="The person asks to revert their previous kitchen change."
    )

    def is_empty(self) -> bool:
        return not (
            self.adds
            or self.consumes
            or self.discards
            or self.updates
            or self.queries
            or self.undo_last
        )

    def item_refs(self) -> list[str]:
        refs = [u.item_ref for u in self.updates]
        refs += [c.item_ref for c in self.consumes]
        refs += [d.item_ref for d in self.discards]
        return list(dict.fromkeys(refs))
