"""Real PDF extraction failures preserve the import error contract."""

from datetime import UTC, datetime
from uuid import uuid4

import pymupdf
import pytest
from finance.adapters.pdf import PymupdfText
from finance.application.categorize import Categorizer
from finance.application.import_statement import ImportStatement
from finance.application.ports import UnreadablePdf
from finance.testing import in_memory_uow
from finance_fixtures import pdf_from
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.skills import Attachment
from shared.testing.fakes import FakeLLM, FixedClock


@pytest.fixture
def encrypted_pdf() -> bytes:
    with pymupdf.open(stream=pdf_from(), filetype="pdf") as doc:
        return bytes(
            doc.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw="owner-password",
                user_pw="user-password",
            )
        )


def test_encrypted_pdf_extraction_raises_unreadable_pdf(encrypted_pdf: bytes) -> None:
    with pytest.raises(UnreadablePdf):
        PymupdfText().extract(encrypted_pdf)


async def test_encrypted_pdf_import_returns_unreadable_pdf(encrypted_pdf: bytes) -> None:
    llm = FakeLLM()
    uow = in_memory_uow()
    skill = ImportStatement(
        pdf=PymupdfText(),
        uow=uow,
        categorize=Categorizer(llm=llm, uow=uow),
        clock=FixedClock(datetime(2026, 11, 2, tzinfo=UTC)),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="en",
    )
    request = SkillRequest(
        task_id="encrypted-pdf",
        context_id="encrypted-pdf",
        text="",
        user_id=uuid4(),
        skill_id="finance.import_statement",
        for_date=None,
        is_peer_call=False,
        attachments=(Attachment(name="encrypted.pdf", mime="application/pdf", data=encrypted_pdf),),
    )
    result = await skill(request, ())
    assert result.failed
    assert result.output == "unreadable_pdf"
    assert not llm.calls
