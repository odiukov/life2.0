"""Plain-text replies for chat (the app renders the screen from structured data)."""

from __future__ import annotations

from collections.abc import Sequence

from shared.ports.translator import Translator

from kitchen.application.service import AppliedChange, ApplyResult, UndoOutcome
from kitchen.domain.model import Batch, ExpirySource, Status
from kitchen.domain.units import humanize_quantity

MAX_NAME = 160
SECTIONS = (
    ("add", "kitchen.added_header"),
    ("update", "kitchen.updated_header"),
    ("consume", "kitchen.consumed_header"),
    ("discard", "kitchen.discarded_header"),
)
CLARIFY_KEYS = {
    "ambiguous": "kitchen.clarify",
    "incompatible_units": "kitchen.clarify_units",
    "invalid_quantity": "kitchen.clarify_quantity",
    "not_found": "kitchen.clarify_not_found",
}
UNDO_KEYS = {
    UndoOutcome.DONE: "kitchen.undone",
    UndoOutcome.ALREADY_UNDONE: "kitchen.undo_already",
    UndoOutcome.CONFLICT: "kitchen.undo_conflict",
    UndoOutcome.NOT_FOUND: "kitchen.undo_not_found",
}


class KitchenText:
    def __init__(self, translator: Translator) -> None:
        self._t = translator

    def text(self, key: str, locale: str, **params: object) -> str:
        return self._t.t(key, locale, **params)

    def _name(self, batch: Batch) -> str:
        name = batch.display_name
        return name if len(name) <= MAX_NAME else name[: MAX_NAME - 1] + "…"

    def _quantity(self, locale: str, batch: Batch) -> dict[str, str]:
        value, unit_key = humanize_quantity(batch.quantity, batch.unit)
        digits = max(0, -int(value.as_tuple().exponent))
        return {
            "quantity": self._t.number(float(value), locale, digits=digits),
            "unit": self._t.t(f"kitchen.units.{unit_key}", locale),
        }

    def _expiry(self, locale: str, batch: Batch) -> str:
        key = (
            "kitchen.expiry_estimated"
            if batch.expiry_source is ExpirySource.ESTIMATED
            else "kitchen.expiry_explicit"
        )
        text = self._t.t(key, locale, date=self._t.date(batch.expires_on, locale))
        if batch.opened:
            text += self._t.t("kitchen.opened_suffix", locale)
        return text

    def line(self, locale: str, batch: Batch) -> str:
        return self._t.t(
            "kitchen.item_line",
            locale,
            name=self._name(batch),
            expiry=self._expiry(locale, batch),
            **self._quantity(locale, batch),
        )

    def _change(self, locale: str, change: AppliedChange) -> str:
        batch = change.after
        if change.op_type == "consume":
            if batch.status is Status.CONSUMED:
                return self._t.t("kitchen.consumed_all", locale, name=self._name(batch))
            return self._t.t(
                "kitchen.consumed_left",
                locale,
                name=self._name(batch),
                **self._quantity(locale, batch),
            )
        if change.op_type == "discard":
            return self._t.t("kitchen.discarded_line", locale, name=self._name(batch))
        if change.op_type == "update":
            return self._t.t(
                "kitchen.updated_line",
                locale,
                name=self._name(batch),
                location=self._t.t(f"kitchen.location.{batch.location.value}", locale),
                expiry=self._expiry(locale, batch),
            )
        return self.line(locale, batch)

    def applied(
        self,
        locale: str,
        result: ApplyResult | None,
        not_found: Sequence[str],
        answers: Sequence[str],
    ) -> str:
        lines: list[str] = []
        if result is not None:
            for op_type, header in SECTIONS:
                group = result.by_type(op_type)
                if group:
                    lines.append(self._t.t(header, locale))
                    lines.extend(self._change(locale, change) for change in group)
        if not_found:
            lines.append(self._t.t("kitchen.not_found", locale, items=", ".join(not_found)))
        lines.extend(answers)
        if result is not None and result.changes:
            lines.append(self._t.t("kitchen.undo_hint", locale))
        return "\n".join(lines) or self._t.t("kitchen.not_understood", locale)

    def clarify(self, locale: str, ref: str, reason: str, candidates: Sequence[str]) -> str:
        key = CLARIFY_KEYS.get(reason, "kitchen.clarify_not_found")
        options = candidates
        if reason == "incompatible_units":
            options = [self._t.t(f"kitchen.units.{unit}", locale) for unit in candidates]
        return self._t.t(key, locale, ref=ref, options=", ".join(options))

    def undo(self, locale: str, outcome: UndoOutcome) -> str:
        return self._t.t(UNDO_KEYS[outcome], locale)
