"""Which peer agents nutrition may consult, and the skill it calls on each (unchanged)."""

PEER_SKILLS: dict[str, str] = {
    "workout": "analyze_workout",
    "body": "analyze_body_trend",
    "sleep": "analyze_sleep",
    "mood": "analyze_mood",
    "medication": "analyze_adherence",
}
