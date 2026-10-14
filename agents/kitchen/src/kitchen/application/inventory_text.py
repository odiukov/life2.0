"""Compact inventory listing used as LLM context."""

from __future__ import annotations

from collections.abc import Sequence

from kitchen.domain.model import Batch


def format_inventory(batches: Sequence[Batch]) -> str:
    lines = []
    for batch in sorted(batches, key=lambda b: (b.name, b.expires_on, b.added_at)):
        lines.append(
            f"- {batch.name} | {batch.display_name} | "
            f"{batch.quantity.normalize():f} {batch.unit.value} | {batch.location.value} | "
            f"opened={'yes' if batch.opened else 'no'} | expires {batch.expires_on.isoformat()}"
        )
    return "\n".join(lines)
