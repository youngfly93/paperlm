"""Unit tests for formula inline/block detection heuristics + placeholder rendering."""

from __future__ import annotations

from markitdown_paperlm.engines.docling_adapter import (
    _INLINE_BLOCK_RATIO,
    _is_inline_formula,
    _record_formula_metadata,
)
from markitdown_paperlm.ir import IR, BBox, Block, BlockType
from markitdown_paperlm.serializers.markdown import MarkdownSerializer

# ---------- _is_inline_formula heuristic ----------


def test_no_bbox_defaults_to_block() -> None:
    assert _is_inline_formula(None, {}) is False


def test_no_page_median_defaults_to_block() -> None:
    bbox = BBox(page=5, x0=0, y0=0, x1=100, y1=20)
    assert _is_inline_formula(bbox, {}) is False


def test_short_formula_with_text_median_is_inline() -> None:
    # height 10, median 8 → ratio 1.25 < 1.5 → inline
    bbox = BBox(page=1, x0=0, y0=100, x1=100, y1=110)
    assert _is_inline_formula(bbox, {1: 8.0}) is True


def test_tall_formula_is_block() -> None:
    # height 30, median 8 → ratio 3.75 >= 1.5 → block
    bbox = BBox(page=1, x0=0, y0=100, x1=200, y1=130)
    assert _is_inline_formula(bbox, {1: 8.0}) is False


def test_ratio_threshold_boundary() -> None:
    """At exactly the ratio threshold, a formula must be block (strict <)."""
    median = 10.0
    threshold_height = _INLINE_BLOCK_RATIO * median
    bbox_at = BBox(page=1, x0=0, y0=0, x1=50, y1=threshold_height)
    bbox_just_under = BBox(page=1, x0=0, y0=0, x1=50, y1=threshold_height - 0.01)
    assert _is_inline_formula(bbox_at, {1: median}) is False
    assert _is_inline_formula(bbox_just_under, {1: median}) is True


# ---------- serializer formula rendering ----------


def test_inline_formula_renders_single_dollars() -> None:
    ir = IR(
        blocks=[
            Block(
                type=BlockType.FORMULA,
                content=r"E = mc^2",
                attrs={"inline": True},
            )
        ]
    )
    out = MarkdownSerializer().render(ir)
    assert "$E = mc^2$" in out
    assert "$$" not in out


def test_block_formula_renders_double_dollars() -> None:
    ir = IR(
        blocks=[
            Block(
                type=BlockType.FORMULA,
                content=r"\int_0^\infty e^{-x} dx",
                attrs={"inline": False},
            )
        ]
    )
    out = MarkdownSerializer().render(ir)
    assert "$$\n\\int_0^\\infty e^{-x} dx\n$$" in out


def test_empty_formula_emits_placeholder() -> None:
    """Formula detected but LaTeX not extracted → placeholder, not drop."""
    ir = IR(
        blocks=[
            Block(type=BlockType.FORMULA, content="", attrs={"inline": False}),
            Block(type=BlockType.FORMULA, content="", attrs={"inline": True}),
        ]
    )
    out = MarkdownSerializer().render(ir)
    assert "$$\n[formula]\n$$" in out
    assert "$[formula]$" in out


def test_formula_block_with_empty_content_still_appears_in_ir() -> None:
    """Regression: previously _item_to_block dropped blocks whose content
    was empty — but FIGURE and FORMULA legitimately have empty content."""
    # Synthesize an IR as if from the adapter
    ir = IR(
        blocks=[
            Block(type=BlockType.PARAGRAPH, content="intro"),
            Block(type=BlockType.FORMULA, content="", attrs={"inline": False}),
            Block(type=BlockType.PARAGRAPH, content="outro"),
        ]
    )
    out = MarkdownSerializer().render(ir)
    assert "intro" in out
    assert "[formula]" in out
    assert "outro" in out
    assert out.index("intro") < out.index("[formula]") < out.index("outro")


def test_formula_metadata_counts_placeholders_and_extracted() -> None:
    ir = IR(
        blocks=[
            Block(type=BlockType.FORMULA, content="", attrs={"inline": False}),
            Block(type=BlockType.FORMULA, content=r"E = mc^2", attrs={"inline": True}),
        ]
    )

    _record_formula_metadata(ir, enable_formula=False)

    assert ir.metadata["formula"] == {
        "enabled": False,
        "detected": 2,
        "extracted": 1,
        "placeholders": 1,
    }
    assert "formula region" in ir.warnings[0]


def test_formula_metadata_does_not_warn_when_formula_enabled() -> None:
    ir = IR(blocks=[Block(type=BlockType.FORMULA, content="", attrs={"inline": False})])

    _record_formula_metadata(ir, enable_formula=True)

    assert ir.metadata["formula"]["enabled"] is True
    assert ir.metadata["formula"]["placeholders"] == 1
    assert ir.warnings == []
