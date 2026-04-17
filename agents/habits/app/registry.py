"""Habit registry CRUD — filled out in Task 3."""
from __future__ import annotations


def normalize_name(raw: str) -> str:
    """Filled out in Task 3."""
    return (raw or "").strip().lower()
