from shared.config import BaseServiceSettings


class RecoverySettings(BaseServiceSettings):
    service_name: str = "agent-recovery"
    recovery_agent_url: str = "http://agent-recovery:8007/"
