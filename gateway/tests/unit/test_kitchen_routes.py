from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Header
from gateway.kitchen import KitchenGateway, build_router
from shared.ports.skills import SkillCallError, SkillReply, SkillUnavailable
from shared.testing.fakes import FakeSkillClient

ITEM = {
    "id": str(uuid4()),
    "name": "молоко",
    "display_name": "молоко",
    "category": "dairy",
    "quantity": "1000.000",
    "unit": "ml",
    "location": "fridge",
    "opened": False,
    "opened_on": None,
    "expires_on": "2026-10-20",
    "expiry_source": "estimated",
    "added_at": "2026-10-13T12:00:00+00:00",
    "added_by": {"user_id": str(uuid4()), "name": "Аня"},
}


async def dev_user(x_user_id: str = Header(alias="X-User-Id")) -> UUID:
    return UUID(x_user_id)


def client(responder) -> tuple[httpx.AsyncClient, FakeSkillClient]:  # type: ignore[no-untyped-def]
    skills = FakeSkillClient(responder)
    app = FastAPI()
    app.include_router(build_router(KitchenGateway(skills), dev_user))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"), skills


H = {"X-User-Id": str(uuid4())}


async def test_inventory_passes_location_and_returns_typed_items() -> None:
    http, skills = client(lambda s, u, p, t: SkillReply("1 items", {"items": [ITEM]}))
    response = await http.get("/kitchen/inventory", params={"location": "fridge"}, headers=H)
    assert response.status_code == 200
    assert response.json()["items"][0]["display_name"] == "молоко"
    assert skills.calls[0][0] == "kitchen.inventory"
    assert skills.calls[0][2] == {"location": "fridge"}


async def test_bad_location_is_rejected_before_calling_the_agent() -> None:
    http, skills = client(lambda s, u, p, t: SkillReply("", {"items": []}))
    response = await http.get("/kitchen/inventory", params={"location": "garage"}, headers=H)
    assert response.status_code == 422
    assert skills.calls == []


@pytest.mark.parametrize(
    ("error", "status", "detail"),
    [
        (SkillUnavailable("down"), 503, "kitchen_unavailable"),
        (SkillCallError("item_gone"), 409, "item_gone"),
        (SkillCallError("invalid_params"), 422, "invalid_params"),
        (SkillCallError("no_household"), 404, "no_household"),
    ],
)
async def test_action_error_mapping(error: Exception, status: int, detail: str) -> None:
    http, _ = client(lambda s, u, p, t: error)
    response = await http.post(
        f"/kitchen/items/{uuid4()}/action", json={"action": "consumed"}, headers=H
    )
    assert (response.status_code, response.json()) == (status, {"detail": detail})


@pytest.mark.parametrize(
    ("code", "status", "detail"),
    [
        ("already_undone", 409, "already_undone"),
        ("conflict", 409, "undo_conflict"),
        ("not_found", 404, "undo_not_found"),
    ],
)
async def test_undo_error_mapping(code: str, status: int, detail: str) -> None:
    http, _ = client(lambda s, u, p, t: SkillCallError(code))
    response = await http.post(f"/kitchen/undo/{uuid4()}", headers=H)
    assert (response.status_code, response.json()) == (status, {"detail": detail})


async def test_action_body_is_forwarded_as_params() -> None:
    http, skills = client(
        lambda s, u, p, t: SkillReply("move", {"group_id": str(uuid4()), "item": ITEM})
    )
    item_id = uuid4()
    response = await http.post(
        f"/kitchen/items/{item_id}/action",
        json={"action": "set_expiry", "expires_on": "2026-10-25"},
        headers=H,
    )
    assert response.status_code == 200
    assert skills.calls[0][2] == {
        "item_id": str(item_id),
        "action": "set_expiry",
        "expires_on": "2026-10-25",
    }


async def test_inventory_without_location_and_digest_use_structured_data() -> None:
    def responder(skill, user, params, text):  # type: ignore[no-untyped-def]
        data = (
            {"items": [ITEM]}
            if skill == "kitchen.inventory"
            else {"expired": [], "today": [ITEM], "tomorrow": [], "soon": []}
        )
        return SkillReply("unrelated analysis text", data)

    http, skills = client(responder)
    async with http:
        inventory = await http.get("/kitchen/inventory", headers=H)
        digest = await http.get("/kitchen/digest", headers=H)
    assert inventory.json()["items"][0]["quantity"] == "1000.000"
    assert digest.json()["today"][0]["id"] == ITEM["id"]
    assert [(s, p) for s, _, p, _ in skills.calls] == [
        ("kitchen.inventory", {}),
        ("kitchen.digest", {}),
    ]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/kitchen/items/bad-uuid/action", {"action": "consumed"}),
        (f"/kitchen/items/{uuid4()}/action", {"action": "bad"}),
        (f"/kitchen/items/{uuid4()}/action", {"action": "move", "location": "garage"}),
        (f"/kitchen/items/{uuid4()}/action", {"action": "set_expiry", "expires_on": "bad"}),
        (f"/kitchen/items/{uuid4()}/action", {"action": "set_quantity", "quantity": "bad"}),
        ("/kitchen/undo/bad-uuid", None),
    ],
)
async def test_bad_request_uses_code_without_calling_peer(path: str, body: object) -> None:
    http, skills = client(lambda s, u, p, t: SkillReply("", {}))
    async with http:
        response = await http.post(path, json=body, headers=H)
    assert (response.status_code, response.json()) == (422, {"detail": "invalid_params"})
    assert skills.calls == []


async def test_bad_location_uses_error_code() -> None:
    http, skills = client(lambda s, u, p, t: SkillReply("", {"items": []}))
    async with http:
        response = await http.get("/kitchen/inventory?location=garage", headers=H)
    assert response.json() == {"detail": "invalid_params"}
    assert skills.calls == []


@pytest.mark.parametrize("data", [None, {}, {"items": [{"id": "broken"}]}])
async def test_malformed_peer_data_is_a_gateway_error(data) -> None:  # type: ignore[no-untyped-def]
    http, _ = client(lambda s, u, p, t: SkillReply("", data))
    async with http:
        response = await http.get("/kitchen/inventory", headers=H)
    assert (response.status_code, response.json()) == (502, {"detail": "kitchen_error"})


async def test_unknown_peer_failure_is_a_gateway_error() -> None:
    http, _ = client(lambda s, u, p, t: SkillCallError("unknown"))
    async with http:
        response = await http.get("/kitchen/digest", headers=H)
    assert (response.status_code, response.json()) == (502, {"detail": "kitchen_error"})


async def test_quantity_and_location_action_params_are_forwarded() -> None:
    http, skills = client(
        lambda s, u, p, t: SkillReply("", {"group_id": str(uuid4()), "item": ITEM})
    )
    item_id = uuid4()
    async with http:
        response = await http.post(
            f"/kitchen/items/{item_id}/action",
            json={"action": "set_quantity", "quantity": "250.500", "location": "freezer"},
            headers=H,
        )
    assert response.status_code == 200
    assert skills.calls[0] == (
        "kitchen.item_action",
        UUID(H["X-User-Id"]),
        {
            "item_id": str(item_id),
            "action": "set_quantity",
            "quantity": "250.500",
            "location": "freezer",
        },
        "",
    )


async def test_undo_success_passes_group_and_returns_done() -> None:
    http, skills = client(lambda s, u, p, t: SkillReply("ignored", {"outcome": "done"}))
    group_id = uuid4()
    async with http:
        response = await http.post(f"/kitchen/undo/{group_id}", headers=H)
    assert response.json() == {"outcome": "done"}
    assert skills.calls[0][0] == "kitchen.undo"
    assert skills.calls[0][2] == {"group_id": str(group_id)}


async def test_http_timeout_becomes_service_unavailable() -> None:
    from shared.adapters.a2a.skill_client import A2ASkillClient

    def timeout(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"]["read"] == 10.0
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as peer:
        app = FastAPI()
        app.include_router(
            build_router(KitchenGateway(A2ASkillClient("http://kitchen/", peer)), dev_user)
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gw"
        ) as http:
            response = await http.get("/kitchen/inventory", headers=H)
    assert (response.status_code, response.json()) == (503, {"detail": "kitchen_unavailable"})
