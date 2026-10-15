from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from body.adapters.vision import ChatModelVision
from body.application.ports import VisionUnavailable
from langchain_core.messages import AIMessage
from shared.ports.llm import LLMTask


async def test_metrics_use_vision_route_and_preserve_multimodal_input() -> None:
    model = Mock(
        ainvoke=AsyncMock(
            return_value=AIMessage(
                content='{"weight_kg": "81.4", "bmi": "invalid", "recorded_at": "2026-10-12T09:06:31"}'
            )
        )
    )
    factory = Mock(chat_model=Mock(return_value=model))
    when, metrics = await ChatModelVision(factory).metrics(b"png")
    assert when == datetime(2026, 10, 12, 9, 6, 31, tzinfo=UTC)
    assert metrics == {"weight_kg": 81.4}
    factory.chat_model.assert_called_once_with(LLMTask.VISION)
    message = model.ainvoke.call_args.args[0][0]
    assert message.content[0] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,cG5n"},
    }


async def test_profile_parses_text_blocks_and_ignores_invalid_fields() -> None:
    model = Mock(
        ainvoke=AsyncMock(
            return_value=AIMessage(
                content=[
                    {"type": "text", "text": '{"sex":"MALE","height_cm":"180","age":"invalid"}'}
                ]
            )
        )
    )
    result = await ChatModelVision(Mock(chat_model=Mock(return_value=model))).profile(b"png")
    assert result == {"sex": "male", "height_cm": 180.0}


async def test_provider_failure_is_a_port_error_without_provider_text() -> None:
    model = Mock(ainvoke=AsyncMock(side_effect=RuntimeError("private provider response")))
    with pytest.raises(VisionUnavailable, match=r"^RuntimeError$"):
        await ChatModelVision(Mock(chat_model=Mock(return_value=model))).metrics(b"png")
