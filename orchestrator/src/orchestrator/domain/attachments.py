from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

MAX_FILES = 4
MAX_IMAGE = 10_000_000
MAX_PDF = 20_000_000
MAX_TOTAL = 25_000_000
MAX_TEXT = 8_000
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
PDF_TYPE = "application/pdf"
FileKind = Literal["payoneer", "vihealth", "unknown"]
_VIHEALTH = (r"Body fat rate", r"LePulse", r"ViHealth", r"Body Mass Index", r"Skeletal muscle")
_PAYONEER = (r"Payoneer", r"Account Statement")


class AttachmentRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class Upload:
    name: str
    mime: str
    data: bytes

    @property
    def is_image(self) -> bool:
        return self.mime in IMAGE_TYPES

    @property
    def is_pdf(self) -> bool:
        return self.mime == PDF_TYPE


def check_uploads(files: Sequence[Upload]) -> list[Upload]:
    if len(files) > MAX_FILES:
        raise AttachmentRejected("too_many_attachments")
    total = 0
    for f in files:
        if not f.data or not (f.is_image or f.is_pdf):
            raise AttachmentRejected("unsupported_attachment")
        if f.is_pdf and not f.data.startswith(b"%PDF-"):
            raise AttachmentRejected("unsupported_attachment")
        if len(f.data) > (MAX_PDF if f.is_pdf else MAX_IMAGE):
            raise AttachmentRejected("attachment_too_large")
        total += len(f.data)
    if total > MAX_TOTAL:
        raise AttachmentRejected("attachment_too_large")
    return list(files)


_VIHEALTH_NAMES = ("lescale", "vihealth", "lepulse")
_PAYONEER_NAMES = ("payoneer",)


def detect_file_kind(text: str, lead_agent: str | None, name: str | None = None) -> FileKind:
    """Ported from legacy file_router: the lead agent is a hint, then the file name, then the text."""
    if lead_agent == "body":
        return "vihealth"
    if lead_agent == "finance":
        return "payoneer"
    lowered = (name or "").lower()
    if any(k in lowered for k in _VIHEALTH_NAMES):
        return "vihealth"
    if any(k in lowered for k in _PAYONEER_NAMES):
        return "payoneer"
    if any(re.search(p, text, re.IGNORECASE) for p in _VIHEALTH):
        return "vihealth"
    if sum(1 for p in _PAYONEER if re.search(p, text, re.IGNORECASE)) >= 2:
        return "payoneer"
    return "unknown"
