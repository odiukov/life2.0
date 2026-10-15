import pymupdf
import pytest
from orchestrator.adapters.documents import PdfDocumentReader
from orchestrator.application.ports import UnreadableDocument


def pdf(pages: int, line: str = "Payoneer Account Statement") -> bytes:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page().insert_text((36, 36), line, fontsize=9)
    data = bytes(doc.tobytes())
    doc.close()
    return data


def test_reads_the_first_pages() -> None:
    assert "Account Statement" in PdfDocumentReader().text(pdf(2))


def test_garbage_and_huge_documents_are_refused() -> None:
    with pytest.raises(UnreadableDocument):
        PdfDocumentReader().text(b"%PDF-1.4 garbage")
    with pytest.raises(UnreadableDocument, match="too_many_pages"):
        PdfDocumentReader().text(pdf(51))


def test_only_first_configured_pages_are_extracted() -> None:
    with pymupdf.open() as doc:
        for line in ["first", "second", "third", "excluded"]:
            doc.new_page().insert_text((36, 36), line)
        result = PdfDocumentReader().text(bytes(doc.tobytes()))
    assert "first" in result
    assert "third" in result
    assert "excluded" not in result
