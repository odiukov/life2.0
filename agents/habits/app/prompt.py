"""Prompt builder for the habits agent — filled out in Task 5."""


async def build_habits_prompt(task: str, params: dict) -> str:
    return f"Task: {task}\nParams: {params}"
