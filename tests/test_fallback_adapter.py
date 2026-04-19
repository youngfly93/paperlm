"""Tests for FallbackAdapter (pdfminer path).

Every test in this module exercises `FallbackAdapter.convert`, which
imports `pdfminer.high_level` lazily. Without pdfminer.six installed,
the adapter's `is_available()` returns False and `convert()` raises
`ModuleNotFoundError` — so we skip the whole module rather than
produce spurious test failures in stripped envs (e.g. a fresh clone
without `pip install -e .`).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip(
    "pdfminer",
    reason="pdfminer.six is a core dep — install via `pip install -e .`",
)

from markitdown_paperlm.engines.base import EngineAdapter  # noqa: E402
from markitdown_paperlm.engines.fallback_adapter import FallbackAdapter  # noqa: E402
from markitdown_paperlm.ir import BlockType  # noqa: E402

FIX = Path(__file__).parent / "fixtures"


def test_fallback_conforms_to_protocol() -> None:
    adapter = FallbackAdapter()
    assert isinstance(adapter, EngineAdapter)
    assert adapter.name == "pdfminer"


def test_fallback_is_available_when_pdfminer_installed() -> None:
    """Fallback only claims availability when pdfminer.six imports.

    pdfminer.six is a core dependency so in any supported install it is
    present. We still check rather than assume.
    """
    try:
        import pdfminer.high_level  # noqa: F401
    except ImportError:
        pytest.skip("pdfminer.six not installed (not in current env)")
    assert FallbackAdapter().is_available() is True


def test_fallback_empty_bytes_returns_warning_ir() -> None:
    adapter = FallbackAdapter()
    ir = adapter.convert(io.BytesIO(b""))
    assert ir.engine_used == "pdfminer"
    # Empty PDF — should warn, not crash
    assert ir.warnings
    assert len(ir.blocks) == 0


@pytest.mark.skipif(
    not (FIX / "sample_en_two_col.pdf").exists(), reason="fixture missing"
)
def test_fallback_on_english_pdf() -> None:
    adapter = FallbackAdapter()
    with open(FIX / "sample_en_two_col.pdf", "rb") as f:
        ir = adapter.convert(f)
    assert ir.engine_used == "pdfminer"
    assert len(ir.blocks) > 5, f"expected >5 paragraph blocks, got {len(ir.blocks)}"
    assert all(b.type == BlockType.PARAGRAPH for b in ir.blocks)
    # Content check — a bioRxiv paper should mention bioinformatics
    all_text = "\n".join(b.content for b in ir.blocks).lower()
    assert "rna" in all_text or "benchmark" in all_text


@pytest.mark.skipif(
    not (FIX / "sample_scanned.pdf").exists(), reason="fixture missing"
)
def test_fallback_on_scanned_pdf_warns() -> None:
    """pdfminer on image-only PDF yields no text → should warn, not crash."""
    adapter = FallbackAdapter()
    with open(FIX / "sample_scanned.pdf", "rb") as f:
        ir = adapter.convert(f)
    assert ir.engine_used == "pdfminer"
    assert len(ir.blocks) == 0
    assert ir.warnings
    assert any("scanned" in w.lower() or "ocr" in w.lower() for w in ir.warnings)


def test_fallback_preserves_stream_position() -> None:
    adapter = FallbackAdapter()
    stream = io.BytesIO(b"not a pdf")
    stream.read(3)  # advance position
    pos_before = stream.tell()
    adapter.convert(stream)
    assert stream.tell() == pos_before
