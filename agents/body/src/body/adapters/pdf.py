from __future__ import annotations

import io

from body.application.ports import UnreadablePdf

MAX_PAGES = 50


class PdfplumberReader:
    def text(self, data: bytes) -> str:
        import pdfplumber

        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                if len(pdf.pages) > MAX_PAGES:
                    raise UnreadablePdf("too_many_pages")
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except UnreadablePdf:
            raise
        except Exception as exc:  # pdfplumber raises pdfminer errors of several types
            raise UnreadablePdf(type(exc).__name__) from None

    def tables(self, data: bytes) -> list[list[list[str | None]]]:
        import pdfplumber

        try:
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return [table for page in pdf.pages for table in page.extract_tables()]
        except Exception as exc:
            raise UnreadablePdf(type(exc).__name__) from None

    def first_page_png(self, data: bytes) -> bytes:
        import pymupdf

        try:
            doc = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
        except Exception as exc:
            raise UnreadablePdf(type(exc).__name__) from None
        try:
            return bytes(doc[0].get_pixmap(matrix=pymupdf.Matrix(2.0, 2.0)).tobytes("png"))  # type: ignore[no-untyped-call]
        except Exception as exc:
            raise UnreadablePdf(type(exc).__name__) from None
        finally:
            doc.close()  # type: ignore[no-untyped-call]
