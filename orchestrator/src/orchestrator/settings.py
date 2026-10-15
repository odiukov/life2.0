from pydantic import Field
from shared.config import BaseServiceSettings


class OrchestratorSettings(BaseServiceSettings):
    service_name: str = "orchestrator"
    checkpointer_pool_max: int = Field(default=5, ge=1)
    recursion_limit: int = Field(default=25, ge=5)
    action_ttl_s: int = Field(default=300, ge=30)
    agent_timeout_s: float = Field(default=60.0, gt=0)
    vision_timeout_s: float = Field(default=30.0, gt=0)
    run_timeout_s: float = Field(default=180.0, gt=0)
