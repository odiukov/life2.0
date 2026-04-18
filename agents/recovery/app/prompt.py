"""Prompt builders for the recovery agent — filled out in Task 5."""


async def build_recovery_prompt(task: str, params: dict) -> str:
    return f"Task: {task}\nParams: {params}"
