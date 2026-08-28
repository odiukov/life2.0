"""Inline /peer provenance chips. The mobile UI's parseAgentTags renderer
turns slash-mentions like "/nutrition" or "/recovery" into coloured AgentMark
chips. This block instructs the LLM to drop one mention right after each
fact taken from a peer agent's section.

Inserted only when the prompt contains non-empty peer_artifacts. Empty
peer_artifacts → omit, so the LLM doesn't manufacture chips for sections
that aren't there.
"""
from __future__ import annotations


PEER_CHIP_RULES: str = """When you reference data that came from a peer agent's section above,
drop a slash-mention right after the fact: e.g. "last meal at 22:30 /nutrition"
or "HRV 42 ms /recovery". The mobile UI renders these as coloured chips.

Rules:
- /name goes immediately after the data point it attributes (or at end of clause).
- One mention per peer per fact is enough.
- DO NOT mention peers whose data you did not actually use.
- DO NOT mention your own agent.
- Only existing agent names: sleep, workout, nutrition, body, mood, habits, recovery, medication.
"""
