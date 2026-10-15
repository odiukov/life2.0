"""Turn a photo into text before the chat model sees the turn. Image bytes go nowhere else."""

from __future__ import annotations

import asyncio
import base64

from langchain_core.messages import HumanMessage
from opentelemetry.instrumentation.utils import suppress_instrumentation
from shared.ports.chat_model import ChatModelFactory
from shared.ports.llm import LLMTask

from orchestrator.application.ports import VisionUnavailable
from orchestrator.domain.attachments import Upload

PROMPT = (
    "Describe what in this photo is relevant to the user's message, in {locale}, in at most 120 words "
    "of plain text. Read any visible text (labels, dates, receipts) exactly. Do not guess what is not "
    "visible.\n\nThe user's message: {question}"
)


class ChatModelImageDescriber:
    def __init__(self, chat_models: ChatModelFactory, *, timeout_s: float) -> None:
        self._chat_models, self._timeout = chat_models, timeout_s

    async def describe(self, image: Upload, question: str, locale: str) -> str:
        url = f"data:{image.mime};base64,{base64.standard_b64encode(image.data).decode()}"
        message = HumanMessage(
            content=[
                {"type": "image_url", "image_url": {"url": url}},
                {
                    "type": "text",
                    "text": PROMPT.format(locale=locale, question=question or "(none)"),
                },
            ]
        )
        try:
            # Image data must not enter LangChain or provider telemetry, even with full capture.
            # Context-local suppression also covers callbacks and resets on failure/cancellation.
            with suppress_instrumentation():
                async with asyncio.timeout(self._timeout):
                    response = await self._chat_models.chat_model(LLMTask.VISION).ainvoke([message])
        except Exception as exc:  # provider errors, unsupported image input, timeouts
            raise VisionUnavailable(type(exc).__name__) from None
        content = response.content
        if isinstance(content, list):
            content = "".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict)
                and b.get("type") == "text"
                and isinstance(b.get("text"), str)
            )
        text = str(content).strip()
        if not text:
            raise VisionUnavailable("empty")
        return text
