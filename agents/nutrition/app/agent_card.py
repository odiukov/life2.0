import os

AGENT_CARD = {
    "name": "nutrition-agent",
    "description": "Logs meals from free text, parses macros with Claude, analyzes nutrition patterns, and gives recommendations tailored to recent workout load.",
    "url": os.environ.get("NUTRITION_AGENT_URL", "http://agent-nutrition:8003"),
    "version": "1.0.0",
    "capabilities": {"streaming": True, "pushNotifications": True},
    "skills": [
        {"id": "log_meal", "name": "Log Meal", "description": "Log a meal from free text and estimate macros", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "analyze_nutrition", "name": "Analyze Nutrition", "description": "Analyze nutrition patterns and macro trends", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "get_recommendations", "name": "Get Recommendations", "description": "Get nutrition recommendations based on recent workout load", "inputModes": ["text"], "outputModes": ["text"]},
    ],
}
