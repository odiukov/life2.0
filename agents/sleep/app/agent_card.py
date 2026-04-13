import os

AGENT_CARD = {
    "name": "sleep-agent",
    "description": "Tracks sleep patterns, analyzes sleep quality, and gives recommendations based on your history.",
    "url": os.environ.get("SLEEP_AGENT_URL", "http://agent-sleep:8001"),
    "capabilities": ["analyze_sleep", "log_sleep", "get_recommendations"],
    "version": "1.0.0",
}
