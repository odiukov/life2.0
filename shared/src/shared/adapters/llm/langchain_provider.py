"""LLMProvider over LangChain chat models: structured output with one repair attempt."""

from __future__ import annotations

import asyncio
from typing import Any

import anthropic
import groq
import httpx
import openai
from google.genai.errors import APIError as GeminiAPIError
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai.chat_models import GoogleRateLimitError

from shared.ports.chat_model import ChatModelFactory
from shared.ports.llm import LLMError, LLMInvalidOutput, LLMTask, LLMUnavailable, SchemaT

REPAIR_PROMPT = (
    "Your previous answer did not match the required schema ({error}). "
    "Answer again with only a value that matches the schema."
)


def text_of(message: object) -> str:
    if message is None:
        return ""
    if not isinstance(message, BaseMessage):
        return repr(message)
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


class LangChainLLMProvider:
    def __init__(self, factory: ChatModelFactory, *, timeout_s: float) -> None:
        self._factory = factory
        self._timeout_s = timeout_s

    async def structured(
        self, *, task: LLMTask, system: str, user: str, schema: type[SchemaT]
    ) -> SchemaT:
        runnable = self._factory.chat_model(task).with_structured_output(schema, include_raw=True)
        messages: list[BaseMessage] = [SystemMessage(system), HumanMessage(user)]
        output = await self._call(runnable, messages)
        parsed = output.get("parsed")
        if isinstance(parsed, schema):
            return parsed
        messages += [
            AIMessage(text_of(output.get("raw"))),
            HumanMessage(REPAIR_PROMPT.format(error=output.get("parsing_error"))),
        ]
        output = await self._call(runnable, messages)
        parsed = output.get("parsed")
        if isinstance(parsed, schema):
            return parsed
        raise LLMInvalidOutput(text_of(output.get("raw")), str(output.get("parsing_error")))

    async def text(self, *, task: LLMTask, system: str, user: str) -> str:
        message = await self._call(
            self._factory.chat_model(task), [SystemMessage(system), HumanMessage(user)]
        )
        answer = text_of(message).strip()
        if not answer:
            raise LLMInvalidOutput("", "empty answer")
        return answer

    async def _call(self, runnable: Any, messages: list[BaseMessage]) -> Any:
        try:
            async with asyncio.timeout(self._timeout_s):
                return await runnable.ainvoke(messages)
        except LLMError:
            raise
        except TimeoutError as exc:
            raise LLMUnavailable("timeout") from exc
        except (
            ConnectionError,
            httpx.NetworkError,
            httpx.TimeoutException,
            httpx.RemoteProtocolError,
            anthropic.APIConnectionError,
            groq.APIConnectionError,
            openai.APIConnectionError,
            GoogleRateLimitError,
        ) as exc:
            raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc
        except (anthropic.APIStatusError, groq.APIStatusError, openai.APIStatusError) as exc:
            if exc.status_code in (408, 409, 429) or exc.status_code >= 500:
                raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc
            raise
        except GeminiAPIError as exc:
            if exc.code in (408, 409, 429) or (exc.code is not None and exc.code >= 500):
                raise LLMUnavailable(f"{type(exc).__name__}: {exc}") from exc
            raise
