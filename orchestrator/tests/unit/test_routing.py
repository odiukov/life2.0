from orchestrator.application.ports import ToolDone
from orchestrator.application.routing import Routing


def test_main_until_an_agent_answers() -> None:
    r = Routing()
    assert (r.primary, r.consulted) == ("main", [])


def test_last_finished_agent_is_primary_and_the_rest_are_consulted_in_order() -> None:
    r = Routing()
    for event in (
        ToolDone("workout"),
        ToolDone("nutrition", ("recovery",)),
        ToolDone("sleep", ("nutrition",)),
    ):
        r.observe(event)
    assert r.primary == "sleep"
    assert r.consulted == ["workout", "nutrition", "recovery"]


def test_repeats_and_non_catalog_tools_are_ignored() -> None:
    r = Routing()
    for event in (ToolDone("sleep"), ToolDone("sync"), ToolDone("sleep", ("sleep",))):
        r.observe(event)
    assert (r.primary, r.consulted) == ("sleep", [])


def test_repeated_agent_finishing_last_becomes_primary():
    routing = Routing()
    for agent in ("sleep", "nutrition", "sleep"):
        routing.observe(ToolDone(agent))
    assert routing.primary == "sleep"
    assert routing.consulted == ["nutrition"]
