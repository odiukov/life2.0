import os

AGENT_CARD = {
    "name": "sleep-agent",
    "description": "Tracks sleep patterns, analyzes sleep quality, and gives recommendations based on your history.",
    "url": os.environ.get("SLEEP_AGENT_URL", "http://agent-sleep:8001"),
    "version": "1.0.0",
    "capabilities": {"streaming": True, "pushNotifications": True},
    "skills": [
        {"id": "analyze_sleep", "name": "Analyze Sleep", "description": "Analyze sleep quality and patterns", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "log_sleep", "name": "Log Sleep", "description": "Log a new sleep entry", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "get_recommendations", "name": "Get Recommendations", "description": "Get sleep improvement recommendations", "inputModes": ["text"], "outputModes": ["text"]},
    ],
}
