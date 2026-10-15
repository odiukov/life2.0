from __future__ import annotations

import io

from orchestrator.application.ports import UnreadableDocument


class PdfDocumentReader:
    """Enough text to tell a Payoneer statement from a ViHealth report (the agents read the rest)."""

    def __init__(self, *, max_pages: int = 3, page_limit: int = 50) -> None:
        self._max_pages, self._limit = max_pages, page_limit

    def text(self, data: bytes) -> str:
        import pdfplumber

        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                if len(pdf.pages) > self._limit:
                    raise UnreadableDocument("too_many_pages")
                return "\n".join(page.extract_text() or "" for page in pdf.pages[: self._max_pages])
        except UnreadableDocument:
            raise
        except Exception as exc:
            raise UnreadableDocument(type(exc).__name__) from None
