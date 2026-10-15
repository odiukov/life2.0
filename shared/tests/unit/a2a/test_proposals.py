import pytest
from shared.a2a.proposals import MAX_SUMMARY, Proposal, from_data, to_data


def test_round_trip() -> None:
    p = Proposal(
        action="calendar.delete", summary="Delete “Gym” today 19:00", payload={"event_id": "e1"}
    )
    assert from_data(to_data(p)) == p
    assert to_data(p)["kind"] == "proposal"


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"kind": "result"},
        {"kind": "proposal", "action": "", "summary": "x", "payload": {}},
        {"kind": "proposal", "action": "a", "summary": "", "payload": {}},
        {"kind": "proposal", "action": "a", "summary": "x" * (MAX_SUMMARY + 1), "payload": {}},
        {"kind": "proposal", "action": "a", "summary": "x", "payload": []},
    ],
)
def test_anything_else_is_not_a_proposal(data) -> None:
    assert from_data(data) is None
