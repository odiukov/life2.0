from datetime import date
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from a2a.server.agent_execution import RequestContext
from a2a.types import Part, TextPart
from shared.a2a.request import (
    InvalidRequest,
    focus_sources,
    read_envelope,
    requested_skill,
    to_request,
)


def ctx(metadata: Any, texts: tuple[str, ...] = ("hello", "world")) -> RequestContext:
    message = SimpleNamespace(
        parts=[Part(root=TextPart(text=t)) for t in texts], metadata=metadata, message_id="m"
    )
    return cast(RequestContext, SimpleNamespace(message=message, task_id="t1", context_id="c1"))


def test_envelope_joins_text_parts_and_keeps_ids() -> None:
    env = read_envelope(ctx({"skillId": "log_meal"}))
    assert (env.task_id, env.context_id, env.text) == ("t1", "c1", "hello\nworld")
    assert requested_skill(env.metadata) == "log_meal"


def test_missing_ids_are_generated() -> None:
    raw = ctx({})
    raw.task_id = None
    env = read_envelope(raw)
    assert len(env.task_id) == 36


def test_object_metadata_is_coerced() -> None:
    meta = SimpleNamespace(skillId="x", focus_sources=["sleep"], is_peer_call=True, for_date=None)
    env = read_envelope(ctx(meta))
    assert requested_skill(env.metadata) == "x"
    assert focus_sources(env.metadata) == ("sleep",)


def test_to_request_parses_user_date_and_peer_flag() -> None:
    uid = uuid4()
    env = read_envelope(
        ctx(
            {
                "user_id": str(uid),
                "for_date": "2026-10-12",
                "is_peer_call": True,
                "params": {"a": 1},
            }
        )
    )
    request = to_request(env, skill_id="analyze_nutrition")
    assert request.user_id == uid
    assert request.for_date == date(2026, 10, 12)
    assert request.is_peer_call is True
    assert request.params == {"a": 1}
    assert request.audit()["for_date"] == "2026-10-12"


@pytest.mark.parametrize("value", ["true", 1, None])
def test_peer_flag_requires_strict_true(value: object) -> None:
    env = read_envelope(ctx({"user_id": str(uuid4()), "is_peer_call": value}))
    assert to_request(env, skill_id="s").is_peer_call is False


def test_bad_for_date_is_ignored() -> None:
    env = read_envelope(ctx({"user_id": str(uuid4()), "for_date": "yesterday"}))
    assert to_request(env, skill_id="s").for_date is None


@pytest.mark.parametrize("metadata", [{}, {"user_id": "not-a-uuid"}, None])
def test_user_id_is_strict(metadata: object) -> None:
    with pytest.raises(InvalidRequest, match="user_id"):
        to_request(read_envelope(ctx(metadata)), skill_id="s")


def test_empty_message_generates_both_ids() -> None:
    from uuid import UUID

    raw = cast(RequestContext, SimpleNamespace(message=None, task_id=None, context_id=None))
    env = read_envelope(raw)
    assert UUID(env.task_id)
    assert UUID(env.context_id)
    assert env.text == ""
    assert env.metadata == {}


def test_non_text_parts_are_ignored() -> None:
    from a2a.types import DataPart

    raw = ctx({})
    raw.message.parts.insert(0, Part(root=DataPart(data={"text": "not text"})))
    assert read_envelope(raw).text == "hello\nworld"


@pytest.mark.parametrize("value", [False, 123, [], {}, object()])
def test_non_uuid_values_raise_invalid_request(value: object) -> None:
    with pytest.raises(InvalidRequest, match="user_id"):
        to_request(read_envelope(ctx({"user_id": value})), skill_id="s")


def test_uuid_object_is_accepted_and_audit_keeps_authoritative_fields() -> None:
    uid = uuid4()
    env = read_envelope(
        ctx({"user_id": uid, "params": {"user_id": "fake", "message": "fake", "x": 2}})
    )
    request = to_request(env, skill_id="s")
    assert request.user_id == uid
    assert request.audit() == {"user_id": str(uid), "message": "hello\nworld", "x": 2}


@pytest.mark.parametrize("value", [None, "sleep", {"sleep": True}, 1])
def test_invalid_focus_sources_are_absent(value: object) -> None:
    assert focus_sources({"focus_sources": value}) is None


def test_focus_sources_keep_only_strings() -> None:
    assert focus_sources({"focus_sources": ["sleep", 1, None]}) == ("sleep",)
