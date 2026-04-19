"""Unit tests for OCR confidence metadata helpers."""

from __future__ import annotations

from markitdown_paperlm.engines.ocr_adapter import (
    LOW_CONFIDENCE_THRESHOLD,
    _finalize_ocr_metadata,
    _record_page_confidence,
)
from markitdown_paperlm.ir import IR


def test_record_page_confidence_adds_page_metadata() -> None:
    ir = IR(engine_used="paddleocr", metadata={"ocr": {"pages": []}})

    _record_page_confidence(ir, page=1, scores=[0.9, 0.8, 1.0])

    page = ir.metadata["ocr"]["pages"][0]
    assert page["page"] == 1
    assert page["line_count"] == 3
    assert page["mean_confidence"] == 0.9
    assert page["min_confidence"] == 0.8
    assert not ir.warnings


def test_record_page_confidence_warns_on_low_confidence() -> None:
    ir = IR(engine_used="paddleocr", metadata={"ocr": {"pages": []}})

    _record_page_confidence(ir, page=2, scores=[0.4, 0.6])

    assert ir.metadata["ocr"]["pages"][0]["mean_confidence"] == 0.5
    assert LOW_CONFIDENCE_THRESHOLD > 0.5
    assert "low OCR confidence" in ir.warnings[0]


def test_record_page_confidence_warns_on_empty_page() -> None:
    ir = IR(engine_used="paddleocr", metadata={"ocr": {"pages": []}})

    _record_page_confidence(ir, page=3, scores=[])

    assert ir.metadata["ocr"]["pages"][0]["mean_confidence"] is None
    assert "produced no text" in ir.warnings[0]


def test_finalize_ocr_metadata_summarizes_pages() -> None:
    ir = IR(engine_used="paddleocr", metadata={"ocr": {"pages": []}})
    _record_page_confidence(ir, page=1, scores=[0.9, 0.8])
    _record_page_confidence(ir, page=2, scores=[0.5])
    _record_page_confidence(ir, page=3, scores=[])

    _finalize_ocr_metadata(ir)

    assert ir.metadata["ocr"]["mean_confidence"] == 0.675
    assert ir.metadata["ocr"]["min_page_confidence"] == 0.5
    assert ir.metadata["ocr"]["low_confidence_pages"] == [2]
    assert ir.metadata["ocr"]["empty_pages"] == [3]
