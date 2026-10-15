from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
import pytest
from body.composition import build_runtime
from body.main import create_app
from body.settings import BodySettings
from body.testing import FakeReportVision
from shared.adapters.a2a.skill_client import A2ASkillClient
from shared.ports.skills import Attachment
from shared.skill_ids import Body
from shared.testing.fakes import FakeLLM, FakePeerClient, InMemoryVectorMemory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


def report_pdf() -> bytes:
    with pymupdf.open() as doc:
        page = doc.new_page()
        fixture = (Path(__file__).parents[1] / "fixtures" / "vihealth_text.txt").read_text()
        page.insert_text((40, 40), fixture)
        for y in (350, 375, 400):
            page.draw_line((40, y), (340, y))
        for x in (40, 190, 340):
            page.draw_line((x, 350), (x, 400))
        page.insert_text((45, 368), "Weight")
        page.insert_text((195, 368), "81.4")
        page.insert_text((45, 393), "Body fat")
        page.insert_text((195, 393), "14.8")
        return doc.tobytes()


async def test_real_pdf_import_is_idempotent_and_tenant_scoped(clean_db: PostgresUrls) -> None:
    me, other = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, name, timezone) VALUES (:a, 'a', 'Europe/Kyiv'), (:b, 'b', 'UTC')"
            ),
            {"a": me, "b": other},
        )
    llm = FakeLLM()
    llm.queue_text("No body measurements available.")
    runtime = build_runtime(
        BodySettings.model_validate({"database": {"dsn": clean_db.rw}}),
        llm=llm,
        peers=FakePeerClient(),
        memory=InMemoryVectorMemory(),
        vision=FakeReportVision(down=True),
    )
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(runtime)), base_url="http://body"
        ) as http:
            client = A2ASkillClient("http://body/", http)
            attachment = Attachment(name="report.pdf", mime="application/pdf", data=report_pdf())
            first = await client.call(
                skill_id=Body.IMPORT_VIHEALTH,
                user_id=me,
                params={"save_profile": True},
                attachments=[attachment],
            )
            second = await client.call(
                skill_id=Body.IMPORT_VIHEALTH,
                user_id=me,
                params={"save_profile": True},
                attachments=[attachment],
            )
            assert first.data["written"] == 1
            assert second.data["unchanged"] == 1
            await client.call(skill_id=Body.GET_LATEST, user_id=other, params={})
        assert "81.4" not in llm.calls[0].user
        async with admin.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT source, data FROM health_logs WHERE user_id=:u AND type='body_composition'"
                    ),
                    {"u": me},
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].source == "vihealth"
            assert rows[0].data["weight_kg"] == 81.4
            profile = (
                await conn.execute(
                    text("SELECT preferences->'body_profile' FROM users WHERE id=:u"), {"u": me}
                )
            ).scalar_one()
            assert profile == {"sex": "male", "age": 35, "height_cm": 180.0}
    finally:
        await runtime.engine.dispose()
        await admin.dispose()
