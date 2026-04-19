"""Targeted tests to close the last-mile coverage gaps on the text-path.

These are the edge branches left uncovered after the main test suite —
things like ``accepts()`` triggered by mimetype rather than extension,
``FOOTNOTE`` block rendering, and various empty-input early-returns. The
goal is to push the text-path coverage to ≥ 95 % without requiring ML
dependencies.
"""

from __future__ import annotations

import io
from unittest.mock import patch

from markitdown import StreamInfo

from markitdown_paperlm._pdf_converter import PaperLMPdfConverter
from markitdown_paperlm.ir import IR, BBox, Block, BlockType
from markitdown_paperlm.serializers.captions import (
    link_captions,
    reorder_captions_after_targets,
)
from markitdown_paperlm.serializers.markdown import MarkdownSerializer
from markitdown_paperlm.serializers.reading_order import repair_two_column_order
from markitdown_paperlm.serializers.tables import (
    merge_cross_page_tables,
    render_gfm_table,
)

# ---------- _pdf_converter.py :61  (accepts() via mimetype only) ----------


def test_accepts_via_mimetype_with_unknown_extension() -> None:
    """``accepts()`` falls through extension check and matches mimetype."""
    conv = PaperLMPdfConverter()
    info = StreamInfo(mimetype="application/pdf", extension=".unknown")
    assert conv.accepts(io.BytesIO(b""), info) is True


def test_accepts_rejects_non_pdf_stream() -> None:
    conv = PaperLMPdfConverter()
    info = StreamInfo(mimetype="text/plain", extension=".txt")
    assert conv.accepts(io.BytesIO(b""), info) is False


def test_accepts_handles_xpdf_mimetype() -> None:
    conv = PaperLMPdfConverter()
    info = StreamInfo(mimetype="application/x-pdf", extension="")
    assert conv.accepts(io.BytesIO(b""), info) is True


# ---------- markdown.py :68-71  (FOOTNOTE block rendering) ----------


def test_footnote_block_renders_as_blockquote() -> None:
    ir = IR(
        blocks=[Block(type=BlockType.FOOTNOTE, content="1. Smith 2020.")]
    )
    out = MarkdownSerializer().render(ir)
    assert "> 1. Smith 2020." in out


def test_footnote_block_empty_content_still_renders_marker() -> None:
    """Empty FOOTNOTE still emits the ``>`` prefix — this is intentional
    so a downstream parser can preserve the structural hint."""
    ir = IR(blocks=[Block(type=BlockType.FOOTNOTE, content="")])
    out = MarkdownSerializer().render(ir)
    assert out.strip().startswith(">")


# ---------- tables.py :32, :106  (cross-page merge edge) ----------


def test_render_gfm_table_with_rows_that_clean_to_nothing() -> None:
    """Rows that contain only whitespace → _normalize_rows drops them all → empty output."""
    out = render_gfm_table([["", " ", "\t"], ["", "", ""]])
    assert out == ""


def test_merge_cross_page_tables_second_has_empty_rows_attr() -> None:
    """If ``attrs['rows']`` is empty on the next TABLE block, merge should bail out early."""
    t1 = Block(
        type=BlockType.TABLE,
        content="| a | b |",
        bbox=BBox(page=1, x0=0, y0=0, x1=100, y1=100),
        attrs={"rows": [["a", "b"], ["1", "2"]]},
    )
    # Second table has no rows data — not a real merge candidate
    t2 = Block(
        type=BlockType.TABLE,
        content="",
        bbox=BBox(page=2, x0=0, y0=0, x1=100, y1=100),
        attrs={"rows": []},
    )
    out = merge_cross_page_tables([t1, t2])
    # Pass-through: both preserved, no merge
    assert len(out) == 2
    assert not out[0].attrs.get("merged_from_pages")


# ---------- captions.py :95 (empty list early return) ----------


def test_reorder_captions_after_targets_empty_input() -> None:
    assert reorder_captions_after_targets([]) == []


def test_link_captions_empty_input() -> None:
    assert link_captions([]) == []


# ---------- reading_order.py :86  (page with only non-bboxed blocks) ----------


def test_repair_two_column_page_with_only_unbboxed_blocks_is_unchanged() -> None:
    blocks = [
        Block(type=BlockType.PARAGRAPH, content=f"p{i}", reading_order=i, bbox=None)
        for i in range(3)
    ]
    out = repair_two_column_order(blocks)
    # No bbox anywhere → no columns to detect → pass-through
    assert [b.content for b in out] == ["p0", "p1", "p2"]


# ---------- scanned_detector.py :63-64  (pdfplumber ImportError branch) ----------


def test_is_scanned_pdf_without_pdfplumber_returns_safe_default() -> None:
    """When pdfplumber is unavailable, detector reports ``is_scanned=False``
    so the router will still attempt text extraction."""
    from markitdown_paperlm.utils import scanned_detector

    # Use a real PDF-ish byte stream to keep pdf_stream.read() happy.
    stream = io.BytesIO(b"%PDF-1.4\n...")

    # Patch the ``pdfplumber`` import inside is_scanned_pdf by making
    # importlib raise ImportError when the adapter asks for it.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pdfplumber":
            raise ImportError("simulated missing pdfplumber")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        result = scanned_detector.is_scanned_pdf(stream)

    assert result.is_scanned is False
    assert "pdfplumber" in result.reason


# ---------- scanned_detector.py :76  (zero-page document) ----------


def test_is_scanned_pdf_zero_page_document() -> None:
    """A PDF with zero pages should report ``is_scanned=False``
    with a ``zero-page document`` reason — not crash."""
    import importlib.util
    if importlib.util.find_spec("pdfplumber") is None:
        import pytest
        pytest.skip("pdfplumber not installed; cannot exercise this branch")

    from markitdown_paperlm.utils import scanned_detector

    # Stub the pdfplumber.open context manager to yield an object whose
    # .pages is empty.
    class _FakePdf:
        pages: list = []
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with patch("pdfplumber.open", return_value=_FakePdf()):
        result = scanned_detector.is_scanned_pdf(io.BytesIO(b"%PDF-1.4\n..."))

    assert result.is_scanned is False
    assert result.pages_checked == 0
    assert "zero-page" in result.reason


# ---------- scanned_detector.py :89-91  (page-level extract_text failure) ----------


def test_is_scanned_pdf_survives_page_level_extract_text_exception() -> None:
    """When a page's ``extract_text`` raises, the detector swallows the error
    and counts that page as empty — the rest of the document continues."""
    import importlib.util
    if importlib.util.find_spec("pdfplumber") is None:
        import pytest
        pytest.skip("pdfplumber not installed; cannot exercise this branch")

    from markitdown_paperlm.utils import scanned_detector

    class _Page:
        def __init__(self, raise_: bool):
            self._raise = raise_
        def extract_text(self):
            if self._raise:
                raise RuntimeError("simulated extraction failure")
            return "hello world this has text"

    class _FakePdf:
        pages = [_Page(raise_=True), _Page(raise_=False), _Page(raise_=True)]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with patch("pdfplumber.open", return_value=_FakePdf()):
        result = scanned_detector.is_scanned_pdf(io.BytesIO(b"%PDF-1.4\n..."))

    # One page yielded text, two failed — detector keeps going.
    assert result.pages_checked == 3
    assert result.total_chars > 0
