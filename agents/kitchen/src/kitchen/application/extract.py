"""Turning a family message into inventory operations with the LLM."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from string import Template

from shared.observability.logging import get_logger
from shared.ports.llm import LLMInvalidOutput, LLMProvider, LLMTask

from kitchen.application.schema import OperationList

logger = get_logger(__name__)


def load_prompt(name: str) -> Template:
    resource = files("kitchen") / "prompts" / f"{name}.md"
    return Template(resource.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class ExtractionContext:
    text: str
    today: date
    timezone: str
    inventory: str
    clarification: str | None = None


async def extract_operations(llm: LLMProvider, ctx: ExtractionContext) -> OperationList | None:
    """None when the model's answer is invalid twice; LLMError when the provider is down."""
    system = load_prompt("extract").substitute(
        today=f"{ctx.today.isoformat()} ({ctx.today.strftime('%A')})",
        timezone=ctx.timezone,
        inventory=ctx.inventory or "(empty)",
        clarification=ctx.clarification or "(none)",
    )
    try:
        return await llm.structured(
            task=LLMTask.KITCHEN_EXTRACT, system=system, user=ctx.text, schema=OperationList
        )
    except LLMInvalidOutput as first:
        repair = (
            f"{ctx.text}\n\n---\nYour previous answer was rejected by the validator:\n"
            f"{first.reason}\nReturn a corrected answer that satisfies the schema."
        )
        try:
            return await llm.structured(
                task=LLMTask.KITCHEN_EXTRACT, system=system, user=repair, schema=OperationList
            )
        except LLMInvalidOutput:
            # Validator errors can contain message content; log only the event.
            logger.warning("kitchen_extraction_invalid")
            return None
