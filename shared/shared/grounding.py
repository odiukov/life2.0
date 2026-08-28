"""Anti-hallucination guardrails appended to every analytical/recommendation
prompt across all 8 peer agents. Replaces the older per-agent ad-hoc rules
with a single source of truth.

Imported by every prompt builder. Tests assert that any LLM-driven prompt
contains GROUNDING_RULES verbatim — see tests/test_grounding_rules_present.py.
"""
from __future__ import annotations


GROUNDING_RULES: str = """GROUNDING RULES — strict:

1. Every numeric claim must reference a number that appears verbatim in the
   sections above. Never invent: dates, durations, kcal, macros, weights,
   heart rates, HRV, sleep stages, body fat %, percentages, or any other metric.

2. Every scientific claim must be grounded in data present in this prompt.
   If you have no data for a metric, you cannot reason from it. State the
   gap instead: "HRV not in data — autonomic recovery uncertain."

3. Forbidden — never produce these:
   - Citations: "according to Walker (2017)", "studies show", "meta-analyses
     suggest". You do not have access to a literature database.
   - Author names, publication years, journal names.
   - Sham precision: "sleep efficiency ~85%" when efficiency was not given.
   - Phantom metrics: cortisol, glucose, insulin, RMSSD, lactate — unless
     explicitly present in the data sections.

4. Allowed — general physiological mechanisms WITHOUT numbers:
   - "Late dinner can delay melatonin onset" — valid framework.
   - "Eccentric load demands more recovery than concentric" — valid framework.
   - These describe mechanisms, not measurements. They cannot include
     fabricated values for the user.

5. Domain isolation:
   - Stay in your own domain for advice. Quote peer data as evidence;
     redirect for cross-domain action ("ask /nutrition for a dinner plan").
   - Never relabel one domain's data as another.
   - If a peer section is missing, do not invent it. If user asked about that
     domain, briefly say data is unavailable and continue with what you have.

6. Confidence honesty:
   - When data is sparse (< 3 entries, baseline unknown), explicitly say so.
     "Two nights isn't enough to detect a trend — log a few more."
   - Never compensate for missing data with confident speculation.
"""
