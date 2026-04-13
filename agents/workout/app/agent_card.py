import os

AGENT_CARD = {
    "name": "workout-agent",
    "description": "Tracks workouts (strength, cycling, combat sports), analyzes training load and progress, and gives recommendations based on history and nutrition.",
    "url": os.environ.get("WORKOUT_AGENT_URL", "http://agent-workout:8002"),
    "capabilities": ["log_workout", "analyze_workout", "get_recommendations"],
    "version": "1.0.0",
}
