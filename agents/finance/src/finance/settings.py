from shared.config import BaseServiceSettings


class FinanceSettings(BaseServiceSettings):
    service_name: str = "agent-finance"
    finance_agent_url: str = "http://agent-finance:8011/"
