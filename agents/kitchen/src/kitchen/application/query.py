"""Answering free questions about the stock."""

from __future__ import annotations

from datetime import date

from shared.ports.llm import LLMProvider, LLMTask

from kitchen.application.extract import load_prompt

LANGUAGE_NAMES = {"ru": "Russian", "en": "English"}


async def answer_query(
    llm: LLMProvider, *, question: str, inventory: str, today: date, locale: str
) -> str:
    system = load_prompt("query").substitute(
        today=today.isoformat(),
        language=LANGUAGE_NAMES.get(locale, "the language of the question"),
        inventory=inventory or "(empty)",
    )
    return await llm.text(task=LLMTask.KITCHEN_QUERY, system=system, user=question)
