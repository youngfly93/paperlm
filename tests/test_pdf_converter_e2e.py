"""End-to-end tests: PaperLMPdfConverter via MarkItDown.

These tests go all the way from ``MarkItDown(enable_plugins=True).convert(pdf)``
through the router, into whatever adapter is installed, and back out to
a rendered Markdown string. The FallbackAdapter (pdfminer) is the last
resort in that chain, so without pdfminer installed there is nothing to
return and the tests would fail. Skip the whole module in that case.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from markitdown import MarkItDown

pytest.importorskip(
    "pdfminer",
    reason="pdfminer.six is a core dep — install via `pip install -e .`",
)

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def md_with_plugin() -> MarkItDown:
    return MarkItDown(enable_plugins=True)


@pytest.mark.skipif(
    not (FIX / "sample_en_two_col.pdf").exists(), reason="fixture missing"
)
def test_e2e_english_paper(md_with_plugin: MarkItDown) -> None:
    result = md_with_plugin.convert(str(FIX / "sample_en_two_col.pdf"))
    assert result.markdown
    # IR attached for Python callers
    assert hasattr(result, "ir")
    assert hasattr(result, "engine_used")
    # Should have run via docling (fallback is "pdfminer")
    assert result.engine_used in ("docling", "pdfminer")
    # Heading hash markers should appear — a sign Docling/serializer worked
    if result.engine_used == "docling":
        assert "#" in result.markdown
        assert "benchmark" in result.markdown.lower()


@pytest.mark.skipif(
    not (FIX / "sample_zh_mixed.pdf").exists(), reason="fixture missing"
)
def test_e2e_chinese_paper(md_with_plugin: MarkItDown) -> None:
    result = md_with_plugin.convert(str(FIX / "sample_zh_mixed.pdf"))
    assert result.markdown
    assert "生物" in result.markdown
    assert hasattr(result, "ir")


@pytest.mark.skipif(
    not (FIX / "sample_scanned_1p.pdf").exists(), reason="fixture missing"
)
def test_e2e_scanned_pdf_routes_through_chain(md_with_plugin: MarkItDown) -> None:
    """Scanned PDF must not crash and should be routed through the degradation chain.

    Uses the 1-page fixture to keep OCR fast. Once Week 2 scanned detection is
    wired, auto mode should route to PaddleOCR (if installed) before Docling.
    """
    result = md_with_plugin.convert(str(FIX / "sample_scanned_1p.pdf"))
    assert result.markdown is not None
    assert hasattr(result, "ir")
    # After Week 2, scanned PDFs may flow to paddleocr; before OCR install
    # they fall through to docling or pdfminer.
    assert result.engine_used in ("paddleocr", "docling", "pdfminer", "failed")


def test_without_plugin_uses_builtin(tmp_path: Path) -> None:
    """Sanity: without enable_plugins=True, the built-in converter runs (not ours)."""
    md_native = MarkItDown(enable_plugins=False)
    if (FIX / "sample_en_two_col.pdf").exists():
        result = md_native.convert(str(FIX / "sample_en_two_col.pdf"))
        # Built-in should not attach our IR
        assert not hasattr(result, "ir")
