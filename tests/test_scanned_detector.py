"""Unit tests for scanned_detector — three-page sampling + safe defaults.

The ``_sample_indices`` pure-math tests run anywhere. The three PDF-based
assertions actually open a fixture via ``pdfplumber`` and must skip when
pdfplumber isn't installed (see per-test ``pdfplumber_required`` marker).
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest

from markitdown_paperlm.utils.scanned_detector import (
    _sample_indices,
    is_scanned_pdf,
)

FIX = Path(__file__).parent / "fixtures"

pdfplumber_required = pytest.mark.skipif(
    importlib.util.find_spec("pdfplumber") is None,
    reason="pdfplumber is a core dep — install via `pip install -e .`",
)


# ---------- page sampling math ----------


@pytest.mark.parametrize(
    "n,expected",
    [
        (1, [0]),
        (2, [0, 1]),
        (3, [0, 1, 2]),
        (4, [0, 2, 3]),
        (10, [0, 5, 9]),
        (100, [0, 50, 99]),
    ],
)
def test_sample_indices(n: int, expected: list[int]) -> None:
    assert _sample_indices(n) == expected


# ---------- corrupt / empty input ----------


def test_empty_bytes_returns_non_scanned() -> None:
    """Corrupt stream → don't pretend it's scanned; caller will deal."""
    r = is_scanned_pdf(io.BytesIO(b""))
    assert r.is_scanned is False
    assert "error" in r.reason.lower() or "pdfplumber" in r.reason.lower()


def test_preserves_stream_position() -> None:
    stream = io.BytesIO(b"garbage")
    stream.read(3)
    pos = stream.tell()
    is_scanned_pdf(stream)
    assert stream.tell() == pos


# ---------- real fixtures ----------


@pdfplumber_required
@pytest.mark.skipif(
    not (FIX / "sample_en_two_col.pdf").exists(), reason="fixture missing"
)
def test_english_pdf_is_not_scanned() -> None:
    with open(FIX / "sample_en_two_col.pdf", "rb") as f:
        r = is_scanned_pdf(f)
    assert r.is_scanned is False
    assert r.avg_chars_per_page > 100
    assert r.pages_checked == 3


@pdfplumber_required
@pytest.mark.skipif(
    not (FIX / "sample_zh_mixed.pdf").exists(), reason="fixture missing"
)
def test_chinese_pdf_is_not_scanned() -> None:
    with open(FIX / "sample_zh_mixed.pdf", "rb") as f:
        r = is_scanned_pdf(f)
    assert r.is_scanned is False
    assert r.avg_chars_per_page > 100


@pdfplumber_required
@pytest.mark.skipif(
    not (FIX / "sample_scanned.pdf").exists(), reason="fixture missing"
)
def test_rasterized_pdf_is_detected_as_scanned() -> None:
    with open(FIX / "sample_scanned.pdf", "rb") as f:
        r = is_scanned_pdf(f)
    assert r.is_scanned is True
    assert r.avg_chars_per_page == 0.0
    assert "threshold" in r.reason
