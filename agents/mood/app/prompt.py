"""Prompt builder for the mood agent — filled out in Task 3."""


async def build_mood_prompt(task: str, params: dict) -> str:
    return f"Task: {task}\nParams: {params}"
