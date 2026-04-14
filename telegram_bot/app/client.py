import os
import httpx

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")
SYNC_SERVICE_URL = os.environ.get("SYNC_SERVICE_URL", "http://sync-service:8080")


async def ask_orchestrator(message: str) -> str:
    """POST message to orchestrator /chat, return the output text."""
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/chat",
                json={"message": message, "params": {}},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("output", str(data))
    except httpx.RequestError as e:
        return f"Orchestrator unavailable: {e}"
    except httpx.HTTPStatusError as e:
        return f"Orchestrator error {e.response.status_code}: {e.response.text[:200]}"


async def sync_body_pdf(payload: dict) -> str:
    """POST extracted body composition payload to sync service, return human-readable result."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{SYNC_SERVICE_URL}/sync/body",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.RequestError as e:
        return f"Sync service unavailable: {e}"
    except httpx.HTTPStatusError as e:
        return f"Sync service error {e.response.status_code}: {e.response.text[:200]}"

    errors = data.get("errors", [])
    synced = data.get("synced", 0)
    skipped = data.get("skipped", 0)

    if errors:
        return f"Error importing body data: {', '.join(errors)}"
    if synced == 0 and skipped > 0:
        return "Body composition data already up to date (no new measurements)."
    return f"Saved {synced} body composition measurement(s) from ViHealth report."
