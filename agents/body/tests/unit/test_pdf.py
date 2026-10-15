from unittest.mock import MagicMock

import pymupdf
import pytest
from body.adapters.pdf import PdfplumberReader
from body.application.ports import UnreadablePdf


@pytest.mark.parametrize("stage", ["page", "pixmap", "png"])
def test_render_failures_translate_and_close_document(
    monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    doc = MagicMock()
    page = doc.__getitem__.return_value
    pixmap = page.get_pixmap.return_value
    operation = {"page": doc.__getitem__, "pixmap": page.get_pixmap, "png": pixmap.tobytes}[stage]
    operation.side_effect = RuntimeError("private PDF content")
    monkeypatch.setattr(pymupdf, "open", MagicMock(return_value=doc))
    with pytest.raises(UnreadablePdf, match=r"^RuntimeError$"):
        PdfplumberReader().first_page_png(b"%PDF-report")
    doc.close.assert_called_once_with()
