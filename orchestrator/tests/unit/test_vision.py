import asyncio

import pytest
from langchain_core.messages import AIMessage
from orchestrator.adapters.vision import ChatModelImageDescriber
from orchestrator.application.ports import VisionUnavailable
from orchestrator.domain.attachments import Upload

PHOTO = Upload("milk.jpg", "image/jpeg", b"\xff\xd8\xff\xe0photo")


class Model:
    def __init__(self, answer: object = "Молоко 3.2%, годен до 20.10", delay: float = 0.0) -> None:
        self.answer, self.delay, self.messages = answer, delay, []

    async def ainvoke(self, messages):  # type: ignore[no-untyped-def]
        self.messages.append(messages)
        await asyncio.sleep(self.delay)
        if isinstance(self.answer, Exception):
            raise self.answer
        return AIMessage(self.answer)


class Models:
    def __init__(self, model: Model) -> None:
        self.model = model

    def chat_model(self, task):  # type: ignore[no-untyped-def]
        return self.model


async def test_describes_the_photo_for_the_question() -> None:
    model = Model()
    text = await ChatModelImageDescriber(Models(model), timeout_s=5).describe(
        PHOTO, "что это?", "ru"
    )  # type: ignore[arg-type]
    assert text == "Молоко 3.2%, годен до 20.10"
    parts = model.messages[0][0].content
    assert parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "что это?" in parts[1]["text"]


@pytest.mark.parametrize("model", [Model(RuntimeError("no vision")), Model(""), Model(delay=1.0)])
async def test_failures_are_vision_unavailable(model: Model) -> None:
    with pytest.raises(VisionUnavailable):
        await ChatModelImageDescriber(Models(model), timeout_s=0.05).describe(PHOTO, "?", "en")  # type: ignore[arg-type]


async def test_provider_error_text_is_not_exposed(caplog) -> None:
    with pytest.raises(VisionUnavailable) as error:
        await ChatModelImageDescriber(
            Models(Model(RuntimeError("private photo payload"))), timeout_s=1
        ).describe(PHOTO, "private question", "en")
    assert "private" not in str(error.value)
    assert "private" not in caplog.text


async def test_text_blocks_are_joined_and_non_text_blocks_ignored() -> None:
    model = Model(
        [
            {"type": "text", "text": "milk"},
            {"type": "reasoning", "text": "private"},
            {"type": "text", "text": " carton"},
        ]
    )
    assert (
        await ChatModelImageDescriber(Models(model), timeout_s=1).describe(PHOTO, "?", "en")
        == "milk carton"
    )
