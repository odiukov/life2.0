"""Kitchen inventory model: one Batch per purchase, not per product."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class Unit(StrEnum):
    PCS = "pcs"
    G = "g"
    ML = "ml"
    PACK = "pack"


class Location(StrEnum):
    FRIDGE = "fridge"
    FREEZER = "freezer"
    PANTRY = "pantry"


class Category(StrEnum):
    DAIRY = "dairy"
    MEAT = "meat"
    FISH = "fish"
    VEGETABLES = "vegetables"
    FRUIT = "fruit"
    BAKERY = "bakery"
    GRAINS = "grains"
    FROZEN = "frozen"
    DRINKS = "drinks"
    SAUCES = "sauces"
    SWEETS = "sweets"
    OTHER = "other"


class Status(StrEnum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    DISCARDED = "discarded"


class ExpirySource(StrEnum):
    EXPLICIT = "explicit"
    ESTIMATED = "estimated"
    CORRECTED = "corrected"


class Source(StrEnum):
    VOICE = "voice"
    TEXT = "text"


@dataclass(slots=True)
class Batch:
    id: UUID | None
    name: str
    display_name: str
    category: Category
    quantity: Decimal
    unit: Unit
    location: Location
    status: Status
    opened: bool
    opened_on: date | None
    added_at: datetime
    added_by: UUID | None
    expires_on: date
    expiry_source: ExpirySource
    next_check_on: date
    source: Source

    @property
    def pk(self) -> UUID:
        if self.id is None:
            raise ValueError("Batch has not been saved yet")
        return self.id
