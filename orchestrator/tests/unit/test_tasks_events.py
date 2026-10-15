import json
from uuid import uuid4

from orchestrator.domain import events
from orchestrator.domain.errors import ErrorCode, message_key
from orchestrator.domain.tasks import TITLE_MAX, task_key, title_from


def test_task_key_and_titles():
    user, task = uuid4(), uuid4()
    assert task_key(user, task) == f"{user}:{task}"
    assert title_from("  hello\nworld ") == "hello world"
    assert title_from("x" * 121) == "x" * (TITLE_MAX - 1) + "…"


def test_wire_events():
    assert events.run_started("t", "r") == {"type": "RunStarted", "threadId": "t", "runId": "r"}
    assert events.run_finished("t", "r")["type"] == "RunFinished"
    assert events.text_start("m")["role"] == "assistant"
    assert events.text_delta("m", "hi")["delta"] == "hi"
    assert events.text_end("m")["messageId"] == "m"
    assert events.agent_routed("sleep")["primary"] == "sleep"
    assert events.agent_consulted(["body"])["peers"] == ["body"]
    assert events.action_proposed("a", "Confirm?", "now")["expiresAt"] == "now"
    assert events.action_resolved("a", "applied", "Done")["status"] == "applied"
    event = events.run_error("timeout", "Timed out")
    encoded = events.sse(event)
    assert encoded.endswith("\n\n")
    assert json.loads(encoded.removeprefix("data: ")) == event
    assert message_key(ErrorCode.TIMEOUT) == "chat.errors.timeout"
