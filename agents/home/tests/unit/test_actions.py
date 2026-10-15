from home.domain.actions import action_key, is_read_only, target


def test_unknown_tools_are_changes() -> None:
    assert is_read_only("GetLiveContext")
    assert not is_read_only("HassTurnOff")
    assert not is_read_only("HassSomethingNew2027")
    assert action_key("HassSomethingNew2027") == "home.proposal.generic"


def test_target_names_what_changes() -> None:
    assert target({"name": "Lamp", "area": "Kitchen"}) == "Lamp, Kitchen"
    assert target({"name": "Lamp", "brightness": 40}) == "Lamp, brightness 40"
    assert target({"temperature": 21}) == "temperature=21"
