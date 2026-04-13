from shared.a2a import A2ATask, A2ATaskRequest, TaskStatus, Artifact, TextPart


def test_task_status_now():
    status = TaskStatus.now("completed")
    assert status.state == "completed"
    assert status.timestamp != ""


def test_a2a_task_serializes():
    task = A2ATask(
        id="test-id",
        status=TaskStatus.now("completed"),
        artifacts=[Artifact(name="result", parts=[TextPart(text="hello")])]
    )
    d = task.model_dump()
    assert d["id"] == "test-id"
    assert d["status"]["state"] == "completed"
    assert d["artifacts"][0]["parts"][0]["text"] == "hello"
    assert d["artifacts"][0]["parts"][0]["type"] == "text"


def test_a2a_task_request_defaults():
    req = A2ATaskRequest(task="analyze_sleep")
    assert req.task == "analyze_sleep"
    assert req.params == {}
    assert req.id == ""


def test_task_status_states():
    for state in ("submitted", "working", "completed", "failed"):
        s = TaskStatus.now(state)
        assert s.state == state
