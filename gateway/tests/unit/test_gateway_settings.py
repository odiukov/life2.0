from gateway.settings import AGENT_URLS, GatewaySettings


def test_nested_agent_url_override_keeps_other_agents(monkeypatch):
    monkeypatch.setenv("DATABASE__DSN", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("AGENT_URLS__FINANCE", "http://custom-finance/")
    settings = GatewaySettings()
    assert settings.agent_urls == {**AGENT_URLS, "finance": "http://custom-finance/"}
    assert settings.kitchen_agent_url == AGENT_URLS["kitchen"]


def test_kitchen_url_alias_and_catalog_stay_in_sync():
    common = {"database": {"dsn": "postgresql://u:p@localhost/db"}}
    catalog = GatewaySettings.model_validate(
        {**common, "agent_urls": {"kitchen": "http://new-kitchen/"}}
    )
    legacy = GatewaySettings.model_validate(
        {**common, "kitchen_agent_url": "http://legacy-kitchen/"}
    )
    assert catalog.kitchen_agent_url == "http://new-kitchen/"
    assert legacy.agent_urls["kitchen"] == "http://legacy-kitchen/"
