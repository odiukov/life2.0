from pydantic import BaseModel
from typing import Any, Literal
from datetime import datetime, timezone

_TaskState = Literal["submitted", "working", "completed", "failed"]


class TaskStatus(BaseModel):
    state: _TaskState
    timestamp: str = ""

    @classmethod
    def now(cls, state: _TaskState) -> "TaskStatus":
        return cls(state=state, timestamp=datetime.now(timezone.utc).isoformat())


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class Artifact(BaseModel):
    name: str
    parts: list[TextPart]


class A2ATask(BaseModel):
    id: str
    status: TaskStatus
    artifacts: list[Artifact] = []


class A2ATaskRequest(BaseModel):
    id: str = ""
    task: str
    params: dict[str, Any] = {}
