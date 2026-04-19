"""Tests for the phase 7 OCR confidence report helpers."""

from __future__ import annotations

from benchmarks.phase7_ocr_confidence_probe import render_report


def test_render_report_includes_page_confidence() -> None:
    report = render_report(
        [
            {
                "fixture": "sample_scanned_1p.pdf",
                "status": "ok",
                "elapsed_s": 12.3,
                "engine_used": "paddleocr",
                "blocks": 45,
                "warnings": [],
                "first_line": "生命科学",
                "ocr": {
                    "mean_confidence": 0.9792,
                    "min_page_confidence": 0.9792,
                    "low_confidence_pages": [],
                    "empty_pages": [],
                    "pages": [
                        {
                            "page": 1,
                            "line_count": 45,
                            "mean_confidence": 0.9792,
                            "min_confidence": 0.9434,
                        }
                    ],
                },
            }
        ]
    )

    assert "sample_scanned_1p.pdf" in report
    assert "0.979" in report
    assert "paddleocr" in report
    assert "45" in report


def test_render_report_handles_missing_ocr_metadata() -> None:
    report = render_report(
        [
            {
                "fixture": "missing.pdf",
                "status": "error",
                "elapsed_s": 0,
                "engine_used": "failed",
                "blocks": 0,
                "warnings": ["fixture missing"],
                "first_line": "",
                "error": "fixture missing",
                "ocr": {},
            }
        ]
    )

    assert "No OCR page metadata" in report
    assert "fixture missing" in report
