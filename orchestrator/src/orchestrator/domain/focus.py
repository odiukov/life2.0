"""Detect explicit cross-domain context in the latest user text."""

import re

_FOCUS_CUE_RE = re.compile(
    r"учитыва|на основе|исходя из|с учё?том|considering|based on|"
    r"given (?:my|the)|in light of|relative to|по отношению к|"
    r"в контексте|in context of",
    re.IGNORECASE,
)

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sleep": ("сон", "сна", "сну", "спал", "сплю", "спан", "sleep", "слипа"),
    "workout": (
        "спорт",
        "тренир",
        "трениров",
        "workout",
        "training",
        "exercise",
        "упражн",
        "кардио",
        "cardio",
        "пробеж",
        "run ",
        "running",
        "лифт",
    ),
    "nutrition": (
        "питан",
        "еда",
        "ел ",
        "ела ",
        "ем ",
        "пищ",
        "калор",
        "kcal",
        "macros",
        "макро",
        "белок",
        "protein",
        "carb",
        "углевод",
        "nutrition",
        "meal",
        "ужин",
        "обед",
        "завтрак",
        "перекус",
        "food",
        "intake",
        "diet ",
        "diet,",
        "diet.",
    ),
    "recovery": (
        "восстан",
        "recovery",
        "hrv",
        "стресс",
        "stress",
        "усталост",
        "readiness",
        "готовност",
        "перетрен",
    ),
}


def autodetect_focus_sources(text: str, primary: str, candidates: tuple[str, ...]) -> list[str]:
    text = text.lower()
    matched: list[str] = []
    for peer in candidates:
        if peer == primary:
            continue
        if any(kw in text for kw in _DOMAIN_KEYWORDS.get(peer, ())):
            matched.append(peer)
    if not matched:
        return []
    cue_present = bool(_FOCUS_CUE_RE.search(text))
    primary_referenced = any(kw in text for kw in _DOMAIN_KEYWORDS.get(primary, ()))
    # cue word OR (multiple domains AND user mentioned the primary domain too)
    # The latter handles an enumeration containing the primary domain.
    if cue_present or (len(matched) >= 1 and primary_referenced):
        return matched
    if len(matched) >= 2:
        return matched
    return []


def merge_focus_sources(
    explicit: list[str] | None,
    auto: list[str],
) -> list[str] | None:
    """Union explicit (LLM-passed) + auto-detected, preserving order, dedup'd."""
    if not explicit and not auto:
        return None
    seen: dict[str, None] = {}
    for src in (explicit or [], auto):
        for peer in src:
            if peer not in seen:
                seen[peer] = None
    return list(seen.keys()) or None
