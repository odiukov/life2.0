import os
import httpx

ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")


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
