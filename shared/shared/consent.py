"""Consent-mode pipeline: ConsentSpanExporter + BaggageSnapshotProcessor.

This file is a stub for Phase 2. Full implementation lands in Phase 6.
`install_consent_pipeline` is a no-op when consent mode isn't active.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def install_consent_pipeline() -> None:
    """Install BaggageSnapshotProcessor + wrap OTLP exporter with ConsentSpanExporter.

    NOT YET IMPLEMENTED. This stub logs a warning when called; consent mode
    is activated but no redaction happens. Full implementation in Task 18.
    """
    log.warning("install_consent_pipeline called but implementation is a stub (Phase 6 wires it up)")
