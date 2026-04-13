import os

AGENT_CARD = {
    "name": "workout-agent",
    "description": "Tracks workouts (strength, cycling, combat sports), analyzes training load and progress, and gives recommendations based on history and nutrition.",
    "url": os.environ.get("WORKOUT_AGENT_URL", "http://agent-workout:8002"),
    "version": "1.0.0",
    "capabilities": {"streaming": True, "pushNotifications": True},
    "skills": [
        {"id": "log_workout", "name": "Log Workout", "description": "Log a new workout session", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "analyze_workout", "name": "Analyze Workout", "description": "Analyze training load, trends, and recovery", "inputModes": ["text"], "outputModes": ["text"]},
        {"id": "get_recommendations", "name": "Get Recommendations", "description": "Recommend next session based on history and context", "inputModes": ["text"], "outputModes": ["text"]},
    ],
}
