"""Integration tests for DoclingAdapter on real fixtures.

These tests load the actual docling model (slow first call) and are
skipped gracefully if docling is not installed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from markitdown_paperlm.engines.docling_adapter import DoclingAdapter
from markitdown_paperlm.ir import BlockType

pytestmark = pytest.mark.skipif(
    not DoclingAdapter().is_available(),
    reason="docling not installed; install with pip install '.[docling]'",
)

FIX = Path(__file__).parent / "fixtures"


def test_docling_is_available() -> None:
    assert DoclingAdapter().is_available()


@pytest.fixture(scope="module")
def adapter() -> DoclingAdapter:
    return DoclingAdapter()


@pytest.mark.skipif(not (FIX / "sample_en_two_col.pdf").exists(), reason="fixture missing")
def test_docling_on_english_double_column(adapter: DoclingAdapter) -> None:
    with open(FIX / "sample_en_two_col.pdf", "rb") as f:
        ir = adapter.convert(f)

    assert ir.engine_used == "docling"
    assert len(ir.blocks) > 0

    # The bioRxiv paper's title should appear as HEADING or TITLE block
    titles = [
        b for b in ir.blocks
        if b.type in (BlockType.TITLE, BlockType.HEADING)
        and "benchmark" in b.content.lower()
    ]
    assert titles, "Expected at least one title/heading containing 'benchmark'"

    # Should have many paragraphs in a 27-page paper
    paragraphs = [b for b in ir.blocks if b.type == BlockType.PARAGRAPH]
    assert len(paragraphs) > 10, f"expected >10 paragraphs, got {len(paragraphs)}"


@pytest.mark.skipif(not (FIX / "sample_zh_mixed.pdf").exists(), reason="fixture missing")
def test_docling_on_chinese_mixed(adapter: DoclingAdapter) -> None:
    with open(FIX / "sample_zh_mixed.pdf", "rb") as f:
        ir = adapter.convert(f)

    assert ir.engine_used == "docling"
    assert len(ir.blocks) > 0

    # Chinese title should appear
    headings = [
        b for b in ir.blocks
        if b.type in (BlockType.TITLE, BlockType.HEADING)
        and "生物" in b.content
    ]
    assert headings, "Expected heading containing 生物"


def test_bbox_populated(adapter: DoclingAdapter) -> None:
    with open(FIX / "sample_zh_mixed.pdf", "rb") as f:
        ir = adapter.convert(f)

    # At least some blocks should have bbox info (Docling provides it)
    with_bbox = [b for b in ir.blocks if b.bbox is not None]
    assert len(with_bbox) > 0, "Expected at least some blocks with bbox"
    b = with_bbox[0]
    assert b.bbox.page >= 1
    assert b.bbox.x1 > b.bbox.x0
