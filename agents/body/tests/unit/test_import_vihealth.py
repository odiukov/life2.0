from pathlib import Path
from uuid import uuid4

import pytest
from body.application.import_vihealth import ImportViHealth
from body.testing import FakeReportReader, FakeReportVision
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.health_logs import HealthLogRepository
from shared.ports.profile import BodyProfileRepository
from shared.ports.skills import Attachment
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    InMemoryBodyProfiles,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

TEXT = (Path(__file__).parents[1] / "fixtures" / "vihealth_text.txt").read_text("utf-8")
TABLES = [[["Weight", "81.4(60.0–81.2)"], ["Body fat", "14.8(9.6–16.0)"]]]
PDF = Attachment(name="LeScale.pdf", mime="application/pdf", data=b"%PDF-1.4 report")
TR = JsonTranslator.from_dir(find_locales_dir())


def build(reader: FakeReportReader, vision: FakeReportVision | None = None):
    logs, profiles, settings = InMemoryHealthLogs(), InMemoryBodyProfiles(), InMemoryUserSettings()
    uow = InMemoryUnitOfWorkFactory(
        {
            HealthLogRepository: logs,
            BodyProfileRepository: profiles,
            UserSettingsRepository: settings,
        }
    )
    skill = ImportViHealth(
        reader=reader,
        vision=vision or FakeReportVision(),
        uow=uow,
        translator=TR,
        default_locale="ru",
    )
    return skill, logs, profiles, vision


def req(user, *files: Attachment, save_profile: bool = False) -> SkillRequest:
    return SkillRequest(
        "t",
        "c",
        "",
        user,
        "body.import_vihealth",
        None,
        False,
        params={"save_profile": save_profile},
        attachments=files,
    )


async def test_text_report_is_stored_once_and_profile_fields_returned() -> None:
    skill, logs, profiles, _ = build(FakeReportReader(TEXT, TABLES))
    user = uuid4()
    first = await skill(req(user, PDF), ())
    again = await skill(req(user, PDF), ())
    assert first.data == {
        "profile_fields": {"sex": "male", "age": 35, "height_cm": 180.0, "weight_kg": 81.4},
        "written": 1,
        "unchanged": 0,
        "recorded_at": "2026-10-12T09:06:31+00:00",
    }
    assert again.data["written"] == 0
    assert again.data["unchanged"] == 1
    rows = await logs.recent(user, types=["body_composition"])
    assert len(rows) == 1
    assert rows[0].source == "vihealth"
    assert rows[0].agent == "body"
    assert rows[0].data["lean_mass_kg"] == 66.6
    assert rows[0].data["bmi"] == 25.1
    assert await profiles.get(user) == {}  # not saved unless asked
    assert TR.t("body.import.written", "ru", count=1) in first.output
    assert TR.t("body.import.weight", "ru", value=81.4) in first.output


async def test_chat_import_saves_height_age_and_sex() -> None:
    skill, _, profiles, _ = build(FakeReportReader(TEXT, TABLES))
    user = uuid4()
    await skill(req(user, PDF, save_profile=True), ())
    assert await profiles.get(user) == {"sex": "male", "age": 35, "height_cm": 180.0}


async def test_image_only_report_uses_vision_and_a_stable_time() -> None:
    vision = FakeReportVision(
        None, {"weight_kg": 80.2, "body_fat_pct": 17.9}, {"sex": "male", "age": 35}
    )
    skill, logs, _, _ = build(FakeReportReader(""), vision)
    user = uuid4()
    await skill(req(user, PDF), ())
    await skill(req(user, PDF), ())
    rows = await logs.recent(user, types=["body_composition"])
    assert len(rows) == 1
    assert rows[0].recorded_at.year >= 2000
    assert vision.calls == 4  # metrics + profile, twice


@pytest.mark.parametrize(
    ("reader", "vision", "files", "code"),
    [
        (FakeReportReader(TEXT, TABLES), None, (), "invalid_params"),
        (
            FakeReportReader(TEXT, TABLES),
            None,
            (Attachment("a.pdf", "application/pdf", b"nope"),),
            "unreadable_pdf",
        ),
        (
            FakeReportReader("Account Statement Payoneer"),
            FakeReportVision(),
            (PDF,),
            "not_a_report",
        ),
        (FakeReportReader(""), FakeReportVision(down=True), (PDF,), "vision_unavailable"),
    ],
)
async def test_failures_are_codes(reader, vision, files, code) -> None:
    skill, *_ = build(reader, vision)
    result = await skill(req(uuid4(), *files), ())
    assert result.failed
    assert result.output == code


async def test_undated_files_with_the_same_fallback_day_do_not_overwrite() -> None:
    vision = FakeReportVision(None, {"weight_kg": 80.2})
    skill, logs, _, _ = build(FakeReportReader(""), vision)
    user = uuid4()
    first = Attachment("a.pdf", "application/pdf", b"%PDF-report-119")
    second = Attachment("b.pdf", "application/pdf", b"%PDF-report-127")
    await skill(req(user, first), ())
    vision._metrics = {"weight_kg": 81.4}
    await skill(req(user, second), ())
    repeated = await skill(req(user, second), ())
    rows = await logs.recent(user, types=["body_composition"])
    assert len(rows) == 2
    assert {row.data["weight_kg"] for row in rows} == {80.2, 81.4}
    assert repeated.data["written"] == 0
    assert repeated.data["unchanged"] == 1


async def test_vision_without_timestamp_preserves_text_measurement_time() -> None:
    skill, logs, _, _ = build(
        FakeReportReader("ViHealth\nMeasuring time\n12 Oct 2026, 09:06:31"),
        FakeReportVision(None, {"weight_kg": 80.2}),
    )
    user = uuid4()
    result = await skill(req(user, PDF), ())
    assert result.data["recorded_at"] == "2026-10-12T09:06:31+00:00"
    rows = await logs.recent(user, types=["body_composition"])
    assert rows[0].recorded_at.isoformat() == "2026-10-12T09:06:31+00:00"
