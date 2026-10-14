from shared.schema import metadata


def test_auth_tables_have_identity_and_rotating_session_keys():
    assert {"auth_identities", "auth_flows", "auth_tickets", "auth_sessions"} <= set(
        metadata.tables
    )
    identities = metadata.tables["auth_identities"]
    assert {"provider", "subject", "user_id"} <= set(identities.c.keys())
    sessions = metadata.tables["auth_sessions"]
    assert {"user_id", "refresh_hash", "expires_at", "revoked_at"} <= set(sessions.c.keys())
    assert "app_challenge" in metadata.tables["auth_flows"].c
    assert "app_challenge" in metadata.tables["auth_tickets"].c
