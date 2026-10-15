"""The calendar agent has no model; free-text routing is refused, structured calls never need it."""

from shared.ports.llm import LLMTask, LLMUnavailable, SchemaT


class NoLLM:
    async def structured(
        self, *, task: LLMTask, system: str, user: str, schema: type[SchemaT]
    ) -> SchemaT:
        raise LLMUnavailable("calendar has no model")

    async def text(self, *, task: LLMTask, system: str, user: str) -> str:
        raise LLMUnavailable("calendar has no model")
