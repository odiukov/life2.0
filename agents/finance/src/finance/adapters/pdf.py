from __future__ import annotations

from finance.application.ports import UnreadablePdf

MAX_PAGES = 50


class PymupdfText:
    def extract(self, data: bytes) -> str:
        import pymupdf

        try:
            doc = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
        except Exception as exc:  # pymupdf raises its own FileDataError and RuntimeError subtypes
            raise UnreadablePdf(type(exc).__name__) from None
        try:
            if doc.page_count > MAX_PAGES:
                raise UnreadablePdf("too_many_pages")
            return "\n".join(page.get_text() for page in doc)  # type: ignore[attr-defined]
        except UnreadablePdf:
            raise
        except Exception as exc:
            raise UnreadablePdf(type(exc).__name__) from None
        finally:
            doc.close()  # type: ignore[no-untyped-call]
