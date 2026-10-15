import pytest
from orchestrator.domain.attachments import (
    MAX_FILES,
    AttachmentRejected,
    Upload,
    check_uploads,
    detect_file_kind,
)

PDF = b"%PDF-1.7\n..."
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 10


def test_accepts_images_and_pdfs() -> None:
    files = check_uploads(
        [Upload("a.jpg", "image/jpeg", JPEG), Upload("s.pdf", "application/pdf", PDF)]
    )
    assert [f.name for f in files] == ["a.jpg", "s.pdf"]


@pytest.mark.parametrize(
    ("files", "code"),
    [
        ([Upload("a.heic", "image/heic", b"x")], "unsupported_attachment"),
        ([Upload("a.pdf", "application/pdf", b"not a pdf")], "unsupported_attachment"),
        ([Upload("a.jpg", "image/jpeg", b"")], "unsupported_attachment"),
        ([Upload("a.jpg", "image/jpeg", JPEG + b"0" * 10_000_000)], "attachment_too_large"),
        (
            [Upload(f"{i}.jpg", "image/jpeg", JPEG) for i in range(MAX_FILES + 1)],
            "too_many_attachments",
        ),
        (
            [
                Upload("a.pdf", "application/pdf", PDF + b"0" * 19_999_000),
                Upload("b.jpg", "image/jpeg", JPEG + b"0" * 6_000_000),
            ],
            "attachment_too_large",
        ),
    ],
)
def test_rejections_have_codes(files, code) -> None:
    with pytest.raises(AttachmentRejected) as error:
        check_uploads(files)
    assert error.value.code == code


def test_detect_file_kind() -> None:
    assert detect_file_kind("LePulse ViHealth Body fat rate 18.2", None) == "vihealth"
    assert detect_file_kind("Payoneer Inc.\nAccount Statement", None) == "payoneer"
    assert detect_file_kind("Account Statement only", None) == "unknown"
    assert detect_file_kind("", "finance") == "payoneer"
    assert detect_file_kind("", "body") == "vihealth"
    assert detect_file_kind("", None, "LeScale_2026-10-12.pdf") == "vihealth"
    assert detect_file_kind("", None, "Payoneer-statement.pdf") == "payoneer"
