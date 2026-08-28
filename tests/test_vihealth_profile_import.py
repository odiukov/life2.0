from orchestrator.app.vihealth_pdf import _extract_profile_from_text


def test_extracts_sex_age_height_weight_single_line():
    text = (
        "Body composition analysis report\n"
        "Gender Age Height\n"
        "Male 31 170 cm\n"
        "Weight 79.6(54.1–73.1) 100.0 Overweight\n"
    )
    result = _extract_profile_from_text(text)
    assert result["sex"] == "male"
    assert result["age"] == 31
    assert result["height_cm"] == 170.0
    assert result["weight_kg"] == 79.6


def test_extracts_female():
    text = (
        "Gender Age Height\n"
        "Female 28 165 cm\n"
        "Weight 60.0(50.0–65.0) 100.0 Normal\n"
    )
    result = _extract_profile_from_text(text)
    assert result["sex"] == "female"
    assert result["age"] == 28
    assert result["height_cm"] == 165.0
    assert result["weight_kg"] == 60.0


def test_returns_empty_for_irrelevant_text():
    result = _extract_profile_from_text("some random unrelated text")
    assert result == {}


def test_fallback_separate_lines():
    text = "Gender\nMale\nAge\n31\nHeight\n170 cm\nWeight\n79.6\n"
    result = _extract_profile_from_text(text)
    assert result.get("sex") == "male"
    assert result.get("age") == 31
    assert result.get("height_cm") == 170.0
    assert result.get("weight_kg") == 79.6


from unittest.mock import MagicMock, patch
import sys


def test_extract_profile_fields_vision_malformed_json():
    """Vision function returns {} on malformed LLM JSON response."""
    from orchestrator.app.vihealth_pdf import _extract_profile_fields_vision

    fake_response = MagicMock()
    fake_response.content = "Sorry, I cannot process this image."

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = fake_response

    fake_pix = MagicMock()
    fake_pix.tobytes.return_value = b"fake-png"
    fake_page = MagicMock()
    fake_page.get_pixmap.return_value = fake_pix
    fake_doc = MagicMock()
    fake_doc.__getitem__ = MagicMock(return_value=fake_page)

    fake_pymupdf = MagicMock()
    fake_pymupdf.open.return_value = fake_doc
    fake_pymupdf.Matrix.return_value = MagicMock()

    fake_shared_llm = MagicMock()
    fake_shared_llm.build_llm.return_value = fake_llm

    with patch.dict(sys.modules, {
        "pymupdf": fake_pymupdf,
        "shared.llm": fake_shared_llm,
        "langchain_core.messages": MagicMock(),
    }):
        result = _extract_profile_fields_vision(b"fake-pdf")

    assert result == {}


def test_extract_profile_fields_vision_fallback():
    """When pdfplumber finds no text, vision LLM is called."""
    from orchestrator.app.vihealth_pdf import extract_profile_fields

    fake_response = MagicMock()
    fake_response.content = '{"weight_kg": 79.6, "height_cm": 170, "age": 31, "sex": "male"}'

    fake_llm = MagicMock()
    fake_llm.invoke.return_value = fake_response

    # Patch pymupdf so we don't need a real PDF
    fake_pix = MagicMock()
    fake_pix.tobytes.return_value = b"fake-png-bytes"
    fake_page = MagicMock()
    fake_page.get_pixmap.return_value = fake_pix
    fake_doc = MagicMock()
    fake_doc.__getitem__ = MagicMock(return_value=fake_page)

    with (
        patch("orchestrator.app.vihealth_pdf.pdfplumber") as mock_plumber,
        patch("orchestrator.app.vihealth_pdf._extract_profile_fields_vision") as mock_vision,
    ):
        # Simulate image-only PDF: pdfplumber returns empty text
        mock_plumber.open.return_value.__enter__.return_value.pages = []
        mock_vision.return_value = {"weight_kg": 79.6, "height_cm": 170.0, "age": 31, "sex": "male"}

        result = extract_profile_fields(b"fake-pdf-bytes")

    mock_vision.assert_called_once_with(b"fake-pdf-bytes")
    assert result["weight_kg"] == 79.6
    assert result["sex"] == "male"
    assert result["age"] == 31
    assert result["height_cm"] == 170.0


import uuid
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_endpoint_rejects_non_pdf():
    from fastapi import HTTPException
    from orchestrator.app.main import import_vihealth_pdf

    mock_file = AsyncMock()
    mock_file.content_type = "text/plain"
    mock_file.filename = "not-a-pdf.txt"
    mock_file.read = AsyncMock(return_value=b"not a pdf")

    with pytest.raises(HTTPException) as exc:
        await import_vihealth_pdf(
            file=mock_file,
            user_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        )
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_endpoint_rejects_payoneer_pdf():
    from fastapi import HTTPException
    from orchestrator.app.main import import_vihealth_pdf

    mock_file = AsyncMock()
    mock_file.content_type = "application/pdf"
    mock_file.filename = "payoneer.pdf"
    mock_file.read = AsyncMock(return_value=b"fake-pdf")

    with patch("orchestrator.app.file_router.detect_file_type", return_value="payoneer"):
        with pytest.raises(HTTPException) as exc:
            await import_vihealth_pdf(
                file=mock_file,
                user_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_endpoint_returns_profile_fields():
    from orchestrator.app.main import import_vihealth_pdf, ViHealthProfileImport

    fake_fields = {"height_cm": 170.0, "weight_kg": 79.6, "age": 31, "sex": "male"}
    mock_file = AsyncMock()
    mock_file.content_type = "application/pdf"
    mock_file.filename = "vihealth.pdf"
    mock_file.read = AsyncMock(return_value=b"fake-pdf")

    with (
        patch("orchestrator.app.file_router.detect_file_type", return_value="vihealth"),
        patch("orchestrator.app.vihealth_pdf.extract_profile_fields", return_value=fake_fields),
        patch("orchestrator.app.file_router._ingest_vihealth", new=AsyncMock(return_value="ok")),
    ):
        result = await import_vihealth_pdf(
            file=mock_file,
            user_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        )

    assert isinstance(result, ViHealthProfileImport)
    assert result.height_cm == 170.0
    assert result.weight_kg == 79.6
    assert result.age == 31
    assert result.sex == "male"
