from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from gateway.profile import build_router
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.profile import BodyProfileRepository
from shared.ports.skills import SkillCallError, SkillReply, SkillUnavailable
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    FakeSkillClient,
    InMemoryBodyProfiles,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

USER = uuid4()
PDF = b"%PDF-1.4 report"


async def me() -> UUID:
    return USER


def app(
    body_client: FakeSkillClient | None = None,
    profiles: InMemoryBodyProfiles | None = None,
    logs: InMemoryHealthLogs | None = None,
) -> FastAPI:
    uow = InMemoryUnitOfWorkFactory(
        {
            BodyProfileRepository: profiles or InMemoryBodyProfiles(),
            HealthLogRepository: logs or InMemoryHealthLogs(),
            UserSettingsRepository: InMemoryUserSettings(),
        }
    )
    api = FastAPI()
    api.include_router(
        build_router(
            uow, body_client or FakeSkillClient(lambda *a: SkillReply("", {})), me, max_bytes=1_000
        )
    )
    return api


async def call(api: FastAPI, method: str, path: str, **kwargs):  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://t"
    ) as client:
        return await client.request(method, path, **kwargs)


async def test_profile_round_trip_with_tdee_and_body_weight() -> None:
    logs = InMemoryHealthLogs()
    logs.seed(
        USER,
        HealthLogRow(
            type="body_composition",
            recorded_at=datetime(2026, 10, 12, tzinfo=UTC),
            data={"weight_kg": 81.4},
            source="vihealth",
            agent="body",
        ),
    )
    api = app(logs=logs)
    patched = await call(
        api,
        "PATCH",
        "/me/profile",
        json={"height_cm": 180, "age": 35, "sex": "male", "activity_level": "moderate"},
    )
    assert patched.json() == {"ok": True}
    got = (await call(api, "GET", "/me/profile")).json()
    assert got["weight_kg"] == 81.4
    assert got["tdee_kcal"]
    assert got["calorie_goal_override"] is None


async def test_patch_validates_and_none_removes() -> None:
    profiles = InMemoryBodyProfiles()
    api = app(profiles=profiles)
    assert (await call(api, "PATCH", "/me/profile", json={"sex": "robot"})).status_code == 422
    assert (await call(api, "PATCH", "/me/profile", json={"age": 500})).status_code == 422
    await call(api, "PATCH", "/me/profile", json={"age": 35, "height_cm": 180})
    await call(api, "PATCH", "/me/profile", json={"age": None})
    assert await profiles.get(USER) == {"height_cm": 180}


async def test_import_pdf_returns_the_fields_and_never_saves_them() -> None:
    body = FakeSkillClient(
        lambda *a: SkillReply(
            "ok",
            {
                "profile_fields": {"sex": "male", "age": 35, "height_cm": 180.0, "weight_kg": 81.4},
                "written": 1,
                "unchanged": 0,
                "recorded_at": "x",
            },
        )
    )
    response = await call(
        app(body),
        "POST",
        "/me/profile/import-pdf",
        files={"file": ("LeScale.pdf", PDF, "application/pdf")},
    )
    assert response.json() == {"height_cm": 180.0, "weight_kg": 81.4, "age": 35, "sex": "male"}
    skill, _, params, _ = body.calls[0]
    assert skill == "body.import_vihealth"
    assert params == {"save_profile": False}
    assert body.attachments[0][0].data == PDF


@pytest.mark.parametrize(
    ("files", "status"),
    [
        ({"file": ("a.pdf", b"not a pdf", "application/pdf")}, 415),
        ({"file": ("a.pdf", b"%PDF-" + b"x" * 2_000, "application/pdf")}, 413),
    ],
)
async def test_import_pdf_checks_the_upload(files, status) -> None:
    assert (await call(app(), "POST", "/me/profile/import-pdf", files=files)).status_code == status


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (SkillCallError("not_a_report"), 422),
        (SkillCallError("unreadable_pdf"), 422),
        (SkillCallError("vision_unavailable"), 503),
        (SkillUnavailable("down"), 503),
    ],
)
async def test_import_pdf_maps_agent_failures(error, status) -> None:
    response = await call(
        app(FakeSkillClient(lambda *a: error)),
        "POST",
        "/me/profile/import-pdf",
        files={"file": ("a.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == status
    assert "Traceback" not in response.text


async def test_profile_ignores_invalid_stored_fields_and_other_agents_weight():
    profiles, logs = InMemoryBodyProfiles(), InMemoryHealthLogs()
    await profiles.update(USER, {"sex": "robot", "activity_level": "invalid", "age": "old"})
    logs.seed(
        USER,
        HealthLogRow(
            type="body_composition",
            recorded_at=datetime(2026, 10, 12, tzinfo=UTC),
            data={"weight_kg": 81.4},
            agent="body",
        ),
    )
    logs.seed(
        USER,
        HealthLogRow(
            type="body_composition",
            recorded_at=datetime(2026, 10, 13, tzinfo=UTC),
            data={"weight_kg": 70},
            agent="nutrition",
        ),
    )
    response = await call(app(profiles=profiles, logs=logs), "GET", "/me/profile")
    assert response.json() == {
        "height_cm": None,
        "weight_kg": 81.4,
        "sex": None,
        "age": None,
        "activity_level": None,
        "calorie_goal_override": None,
        "tdee_kcal": None,
    }


async def test_profile_weight_override_wins_and_null_restores_body_measurement():
    logs = InMemoryHealthLogs()
    logs.seed(
        USER,
        HealthLogRow(
            type="body_composition",
            recorded_at=datetime(2026, 10, 12, tzinfo=UTC),
            data={"weight_kg": 81.4},
            agent="body",
        ),
    )
    api = app(logs=logs)
    await call(api, "PATCH", "/me/profile", json={"weight_kg": 75})
    assert (await call(api, "GET", "/me/profile")).json()["weight_kg"] == 75
    await call(api, "PATCH", "/me/profile", json={"weight_kg": None})
    assert (await call(api, "GET", "/me/profile")).json()["weight_kg"] == 81.4


async def test_profile_non_finite_legacy_values_are_ignored():
    profiles = InMemoryBodyProfiles()
    await profiles.update(USER, {"height_cm": float("inf"), "weight_kg": float("nan")})
    response = await call(app(profiles=profiles), "GET", "/me/profile")
    assert response.status_code == 200
    assert response.json()["height_cm"] is None
    assert response.json()["weight_kg"] is None


async def test_large_pdf_stream_is_rejected_before_consuming_the_whole_body():
    body = FakeSkillClient(lambda *a: SkillReply("", {}))
    consumed = []
    boundary = "profile-boundary"

    async def chunks():
        parts = [
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="report.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
            ).encode(),
            b"%PDF-" + b"x" * 40_000,
            b"y" * 40_000,
            b"z" * 40_000,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        for index, part in enumerate(parts):
            consumed.append(index)
            yield part

    response = await call(
        app(body),
        "POST",
        "/me/profile/import-pdf",
        content=chunks(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert (response.status_code, response.json()) == (413, {"detail": "file_too_large"})
    assert consumed == [0, 1, 2]
    assert body.calls == []


async def test_declared_large_pdf_is_rejected_without_reading_body():
    body = FakeSkillClient(lambda *a: SkillReply("", {}))
    consumed = False

    async def chunks():
        nonlocal consumed
        consumed = True
        yield b"small"

    response = await call(
        app(body),
        "POST",
        "/me/profile/import-pdf",
        content=chunks(),
        headers={"Content-Type": "multipart/form-data", "Content-Length": "1000000"},
    )
    assert (response.status_code, response.json()) == (413, {"detail": "file_too_large"})
    assert not consumed
    assert body.calls == []
