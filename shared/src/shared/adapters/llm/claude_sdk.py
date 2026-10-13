"""LLMProvider backed by the Claude Agent SDK (uses the local Claude Code login).

For personal self-hosting only: a subscription login must not be offered to other people.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

from claude_agent_sdk import (
    CLIConnectionError,
    CLINotFoundError,
    ClaudeAgentOptions,
    ProcessError,
    ResultMessage,
    query,
)
from opentelemetry import trace
from pydantic import ValidationError

from shared.adapters.llm.json_extract import extract_json
from shared.ports.llm import LLMInvalidOutput, LLMTask, LLMUnavailable, SchemaT

tracer = trace.get_tracer("shared.llm.claude_sdk")


class ClaudeSdkLLMProvider:
    def __init__(self, *, models: Mapping[LLMTask, str], timeout_s: float) -> None:
        self._models = dict(models)
        self._timeout_s = timeout_s

    async def structured(
        self, *, task: LLMTask, system: str, user: str, schema: type[SchemaT]
    ) -> SchemaT:
        options = self._options(task, system)
        options.output_format = {"type": "json_schema", "schema": schema.model_json_schema()}
        result = await self._run(user, options, task)
        data = result.structured_output
        if data is None:
            try:
                data = extract_json(result.result or "")
            except ValueError as exc:
                raise LLMInvalidOutput(result.result or "", str(exc)) from exc
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise LLMInvalidOutput(
                json.dumps(data, ensure_ascii=False, default=str), str(exc)
            ) from exc

    async def text(self, *, task: LLMTask, system: str, user: str) -> str:
        result = await self._run(user, self._options(task, system), task)
        answer = (result.result or "").strip()
        if not answer:
            raise LLMInvalidOutput("", "empty answer")
        return answer

    def _options(self, task: LLMTask, system: str) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            system_prompt=system,
            model=self._models[task],
            tools=[],
            max_turns=3,
            setting_sources=[],
        )

    async def _run(self, prompt: str, options: ClaudeAgentOptions, task: LLMTask) -> ResultMessage:
        with tracer.start_as_current_span("llm.claude_sdk") as span:
            span.set_attribute("llm.model_name", options.model or "")
            span.set_attribute("llm.task", task.value)
            result: ResultMessage | None = None
            try:
                async with asyncio.timeout(self._timeout_s):
                    async for message in query(prompt=prompt, options=options):
                        if isinstance(message, ResultMessage):
                            result = message
            except TimeoutError as exc:
                raise LLMUnavailable("timeout") from exc
            except CLINotFoundError:
                raise
            except (CLIConnectionError, ProcessError) as exc:
                raise LLMUnavailable(str(exc)) from exc
            if result is None or result.is_error:
                raise LLMUnavailable(result.subtype if result else "no result message")
            if result.usage:
                for key in ("input_tokens", "output_tokens"):
                    value = result.usage.get(key)
                    if isinstance(value, int):
                        span.set_attribute(f"llm.token_count.{key.split('_')[0]}", value)
            return result
