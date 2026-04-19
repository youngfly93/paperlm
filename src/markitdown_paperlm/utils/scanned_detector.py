"""Heuristic detection of scanned (image-only) PDFs.

Strategy: sample the first, middle, and last page with pdfplumber;
if total extractable text is below a low threshold, the document is
almost certainly a scan that needs OCR. We deliberately skip the
*entire* text layer scan because a 500-page scanned PDF would make
that path slow.

This mirrors the approach used by markitdown-ocr at
_pdf_converter_with_ocr.py:307 (empty-text = scan).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import BinaryIO

logger = logging.getLogger(__name__)

# Pages with < this many chars of extractable text are treated as "empty".
DEFAULT_MIN_CHARS_PER_PAGE = 50

# A doc is "scanned" if avg chars/sampled-page < this threshold.
DEFAULT_SCAN_THRESHOLD = 20


@dataclass
class ScanCheckResult:
    is_scanned: bool
    total_chars: int
    pages_checked: int
    avg_chars_per_page: float
    reason: str


def is_scanned_pdf(
    pdf_stream: BinaryIO,
    *,
    min_chars_per_page: int = DEFAULT_MIN_CHARS_PER_PAGE,
    scan_threshold: int = DEFAULT_SCAN_THRESHOLD,
) -> ScanCheckResult:
    """Decide whether a PDF stream is scanned (image-only).

    Samples up to 3 pages (first, middle, last) and counts extractable chars.
    Returns a ScanCheckResult with the verdict and per-metric reason.

    Stream position is restored on return.

    Never raises — on error we conservatively return is_scanned=False so
    the caller attempts text extraction anyway.
    """
    cur = pdf_stream.tell()
    try:
        pdf_stream.seek(0)
        buf = io.BytesIO(pdf_stream.read())
    finally:
        pdf_stream.seek(cur)

    try:
        import pdfplumber
    except ImportError:
        return ScanCheckResult(
            is_scanned=False,
            total_chars=0,
            pages_checked=0,
            avg_chars_per_page=0.0,
            reason="pdfplumber not installed; cannot detect",
        )

    try:
        with pdfplumber.open(buf) as pdf:
            n = len(pdf.pages)
            if n == 0:
                return ScanCheckResult(
                    is_scanned=False,
                    total_chars=0,
                    pages_checked=0,
                    avg_chars_per_page=0.0,
                    reason="zero-page document",
                )

            sample_indices = _sample_indices(n)
            total_chars = 0
            for i in sample_indices:
                try:
                    text = pdf.pages[i].extract_text() or ""
                except Exception as exc:  # page-level failure
                    logger.debug("page %d extract_text failed: %s", i, exc)
                    text = ""
                total_chars += len(text.strip())

            pages_checked = len(sample_indices)
            avg = total_chars / pages_checked if pages_checked else 0.0

            is_scanned = avg < scan_threshold
            reason = (
                f"avg {avg:.1f} chars/page across {pages_checked} sampled "
                f"(threshold {scan_threshold})"
            )
            return ScanCheckResult(
                is_scanned=is_scanned,
                total_chars=total_chars,
                pages_checked=pages_checked,
                avg_chars_per_page=avg,
                reason=reason,
            )
    except Exception as exc:
        logger.warning("scanned detection failed, assuming not scanned: %s", exc)
        return ScanCheckResult(
            is_scanned=False,
            total_chars=0,
            pages_checked=0,
            avg_chars_per_page=0.0,
            reason=f"detection error: {exc}",
        )


def _sample_indices(n_pages: int) -> list[int]:
    """Return up to 3 representative page indices: first, middle, last."""
    if n_pages <= 3:
        return list(range(n_pages))
    return [0, n_pages // 2, n_pages - 1]
