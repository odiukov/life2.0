import os

AGENT_CARD = {
    "name": "nutrition-agent",
    "description": "Logs meals from free text, parses macros with Claude, analyzes nutrition patterns, and gives recommendations tailored to recent workout load.",
    "url": os.environ.get("NUTRITION_AGENT_URL", "http://agent-nutrition:8003"),
    "capabilities": ["log_meal", "analyze_nutrition", "get_recommendations"],
    "version": "1.0.0",
}
