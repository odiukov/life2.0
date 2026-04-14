from orchestrator.app.main import app


def _route_paths() -> set[str]:
    return {getattr(r, "path", None) for r in app.routes}


def test_agui_route_registered():
    paths = _route_paths()
    agui_paths = {p for p in paths if p and p.startswith("/agui")}
    assert agui_paths, f"no /agui route registered; got {sorted(p for p in paths if p)}"


def test_old_copilotkit_route_removed():
    paths = _route_paths()
    copilotkit_paths = {p for p in paths if p and p.startswith("/copilotkit")}
    assert not copilotkit_paths, f"/copilotkit route should be gone; got {copilotkit_paths}"
