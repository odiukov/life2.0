"""Guards on the orchestrator system prompt — future edits must not drop these."""

import re


def _get_system_prompt():
    """Extract _SYSTEM_PROMPT from source to avoid import issues."""
    with open('orchestrator/app/health_agent.py', 'r') as f:
        content = f.read()
    # Match the full _SYSTEM_PROMPT tuple definition
    match = re.search(r'_SYSTEM_PROMPT = \(([\s\S]*?)\)\s*\n\s*\n\s*async def', content)
    if not match:
        raise ValueError("Could not find _SYSTEM_PROMPT definition")
    prompt_content = match.group(1)
    # Extract string literals and concatenate them
    string_literals = re.findall(r'"((?:\\.|[^"\\])*)"', prompt_content)
    prompt = ''.join(string_literals)
    # Process escape sequences
    prompt = prompt.replace('\\n', '\n')
    return prompt


def test_system_prompt_mentions_six_peer_agents():
    prompt = _get_system_prompt()
    assert "six" in prompt.lower() or "6" in prompt or "seven" in prompt.lower() or "7" in prompt
    for agent in ("sleep", "workout", "nutrition", "body", "mood", "habits"):
        assert agent in prompt, f"Agent '{agent}' not found in system prompt"


def test_system_prompt_has_habits_command_only_guard():
    """From habits-tracker T12 — must survive future edits."""
    prompt = _get_system_prompt()
    assert "/habit" in prompt, "'/habit' command guard not found"
    assert "NOT" in prompt or "must not" in prompt.lower(), "Habit guard negation not found"


def test_system_prompt_mentions_calendar_tools():
    prompt = _get_system_prompt()
    lower = prompt.lower()
    assert "calendar" in lower, "Calendar not mentioned in system prompt"
    assert any(kw in lower for kw in ("list events", "what's on", "find free", "when am i free")), \
        "Calendar routing intents not found"


def test_system_prompt_has_destructive_ops_safety_clause():
    """LLM must paraphrase + confirm before create/update/delete."""
    prompt = _get_system_prompt()
    lower = prompt.lower()
    destructive = sum(verb in lower for verb in ("create", "update", "delete"))
    assert destructive >= 2, f"Not enough destructive operations mentioned (found {destructive})"
    assert any(kw in lower for kw in ("confirm", "paraphrase", "ask before")), \
        "Safety clause confirmation keywords not found"
