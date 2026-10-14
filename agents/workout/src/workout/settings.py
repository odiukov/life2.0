from shared.config import BaseServiceSettings


class WorkoutSettings(BaseServiceSettings):
    service_name: str = "agent-workout"
    workout_agent_url: str = "http://agent-workout:8002/"
