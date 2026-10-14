from shared.config import BaseServiceSettings


class MedicationSettings(BaseServiceSettings):
    service_name: str = "agent-medication"
    medication_agent_url: str = "http://agent-medication:8008/"
