"""The one prompt layout of every health analysis skill (nutrition's layout, generalized)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from shared.analysis.chip_rules import PEER_CHIP_RULES
from shared.analysis.grounding import GROUNDING_RULES
from shared.analysis.personas import IDENTITY, VOCAB


@dataclass(frozen=True, slots=True)
class PromptSection:
    title: str
    body: str
    after_peers: bool = False

    def render(self) -> str:
        return f"## {self.title}\n{self.body}"


@dataclass(frozen=True, slots=True)
class PromptInputs:
    agent: str
    mode: str
    sections: Sequence[PromptSection]
    peers: Mapping[str, str]
    peer_order: Sequence[str]
    memories: Sequence[str] | None  # None: the agent does not use memories in prompts
    message: str
    tail: str
    focus_date: date | None = None


def _focus(day: date) -> str:
    return (
        f"## Peer-consult focus date: {day}\n"
        f"This call is from another agent that needs context for {day} specifically. "
        "Prioritize entries on or around this date; mention the broader trend only if directly relevant."
    )


def compose_prompt(inputs: PromptInputs) -> tuple[str, str]:
    system = (
        f"{IDENTITY[inputs.agent]}\n\n"
        f"## Vocabulary you may invoke (only when grounded by data)\n{VOCAB[inputs.agent]}\n\n"
        f"{GROUNDING_RULES}"
    )
    chunks = [
        f"### {name}\n{inputs.peers[name]}"
        for name in inputs.peer_order
        if inputs.peers.get(name, "").strip()
    ]
    peer_section = "\n## Peer context\n" + "\n\n".join(chunks) + "\n" if chunks else ""
    parts = [s.render() for s in inputs.sections if not s.after_peers]
    if inputs.focus_date is not None:
        parts.append(_focus(inputs.focus_date))
    parts.append(peer_section)
    parts.extend(s.render() for s in inputs.sections if s.after_peers)
    if inputs.memories is not None:
        memories = "\n".join(f"- {text}" for text in inputs.memories) or "No relevant memories."
        parts.append(f"## Memories\n{memories}")
    parts.append(f"## User request\nTask: {inputs.mode}\nMessage: {inputs.message}")
    parts.append(PEER_CHIP_RULES if chunks else "")
    parts.append(inputs.tail)
    return system, "\n\n".join(part for part in parts if part)
