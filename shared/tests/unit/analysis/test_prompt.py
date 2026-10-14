from datetime import date

from shared.analysis.chip_rules import PEER_CHIP_RULES
from shared.analysis.grounding import GROUNDING_RULES
from shared.analysis.personas import IDENTITY, VOCAB
from shared.analysis.prompt import PromptInputs, PromptSection, compose_prompt


def inputs(**kw: object) -> PromptInputs:
    values: dict[str, object] = {
        "agent": "sleep",
        "mode": "analyze_sleep",
        "sections": [PromptSection("Recent sleep", "- 2026-10-12 | 7h")],
        "peers": {},
        "peer_order": ("workout", "mood"),
        "memories": ["slept badly after late runs"],
        "message": "как я сплю?",
        "tail": "Respond in 6–10 lines plain text.",
    }
    values.update(kw)
    return PromptInputs(**values)  # type: ignore[arg-type]


def test_system_is_identity_vocab_grounding() -> None:
    system, _ = compose_prompt(inputs())
    assert system == (
        f"{IDENTITY['sleep']}\n\n## Vocabulary you may invoke (only when grounded by data)\n"
        f"{VOCAB['sleep']}\n\n{GROUNDING_RULES}"
    )


def test_user_layout_without_peers() -> None:
    _, user = compose_prompt(inputs())
    assert user == (
        "## Recent sleep\n- 2026-10-12 | 7h\n\n"
        "## Memories\n- slept badly after late runs\n\n"
        "## User request\nTask: analyze_sleep\nMessage: как я сплю?\n\n"
        "Respond in 6–10 lines plain text."
    )
    assert PEER_CHIP_RULES not in user


def test_peers_follow_peer_order_skip_blank_and_bring_chip_rules() -> None:
    _, user = compose_prompt(
        inputs(peers={"mood": "calm week", "workout": "  ", "nutrition": "ignored"})
    )
    assert "\n## Peer context\n### mood\ncalm week\n" in user
    assert "### workout" not in user
    assert "### nutrition" not in user
    assert PEER_CHIP_RULES in user
    assert user.index("## Peer context") < user.index("## Memories")


def test_after_peers_sections_and_disabled_memories() -> None:
    _, user = compose_prompt(
        inputs(
            sections=[PromptSection("A", "a"), PromptSection("B", "b", after_peers=True)],
            peers={"mood": "x"},
            memories=None,
        )
    )
    assert user.index("## A") < user.index("## Peer context") < user.index("## B")
    assert "## Memories" not in user


def test_empty_memories_say_so_and_focus_date_is_announced() -> None:
    _, user = compose_prompt(inputs(memories=[], focus_date=date(2026, 10, 12)))
    assert "## Memories\nNo relevant memories." in user
    assert "## Peer-consult focus date: 2026-10-12" in user
    assert "Params:" not in user
