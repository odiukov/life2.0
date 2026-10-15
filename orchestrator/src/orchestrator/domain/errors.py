from enum import StrEnum


class ErrorCode(StrEnum):
    AGENT_UNAVAILABLE = "agent_unavailable"
    TIMEOUT = "timeout"
    TASK_BUSY = "task_busy"
    UNSUPPORTED_ATTACHMENT = "unsupported_attachment"
    INTERNAL = "internal"


def message_key(code: str) -> str:
    return f"chat.errors.{code}"
