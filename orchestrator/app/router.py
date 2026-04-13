INTENT_KEYWORDS: dict[str, list[str]] = {
    "sleep": ["sleep", "спал", "сон", "засыпал", "проснул", "ночь"],
    "workout": ["workout", "трениров", "пробеж", "run", "exercise", "спорт", "фитнес"],
    "nutrition": ["nutrition", "еда", "ел", "питание", "meal", "food", "калори"],
}


def classify_intent(message: str) -> str:
    lower = message.lower()
    for agent, keywords in INTENT_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return agent
    return "sleep"  # default
