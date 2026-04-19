"""Tests for two-column reading-order repair."""

from __future__ import annotations

from markitdown_paperlm.ir import BBox, Block, BlockType
from markitdown_paperlm.serializers.reading_order import (
    MIN_COLUMN_GAP,
    _two_column_split,
    repair_two_column_order,
)


def _block(
    text: str,
    order: int,
    *,
    page: int = 1,
    x0: float = 0,
    y0: float = 0,
    x1: float = 100,
    y1: float = 20,
) -> Block:
    return Block(
        type=BlockType.PARAGRAPH,
        content=text,
        bbox=BBox(page=page, x0=x0, y0=y0, x1=x1, y1=y1),
        reading_order=order,
    )


# ---------- _two_column_split ----------


def test_single_column_returns_none() -> None:
    xs = [50, 55, 52, 49, 51, 53]
    assert _two_column_split(sorted(xs)) is None


def test_two_wide_clusters_return_split() -> None:
    # Left column at ~50, right column at ~350. Gap is 300 pt.
    xs = sorted([50, 55, 52, 350, 355, 352])
    split = _two_column_split(xs)
    assert split is not None
    assert 55 < split < 350


def test_gap_below_threshold_returns_none() -> None:
    xs = sorted([50, 60, 80, 100])  # no gap > MIN_COLUMN_GAP
    assert _two_column_split(xs) is None
    # Confirm the test fixture matches the threshold we're using
    assert MIN_COLUMN_GAP > 20


def test_two_widely_spaced_items_split_at_midpoint() -> None:
    """Two x-starts with a big gap do yield a split (midpoint).
    The repair function's ``len(page_blocks) < 3`` guard prevents us from
    acting on such sparse pages anyway."""
    assert _two_column_split([50, 350]) == 200.0


def test_single_item_never_splits() -> None:
    assert _two_column_split([50]) is None
    assert _two_column_split([]) is None


# ---------- repair_two_column_order ----------


def test_empty_input() -> None:
    assert repair_two_column_order([]) == []


def test_single_column_page_unchanged() -> None:
    blocks = [
        _block("a", 0, y0=10, x0=50),
        _block("b", 1, y0=30, x0=52),
        _block("c", 2, y0=50, x0=51),
    ]
    out = repair_two_column_order(blocks)
    assert [b.content for b in out] == ["a", "b", "c"]


def test_two_column_page_is_repaired() -> None:
    """Input is interleaved (left-top, right-top, left-bottom, right-bottom)
    which is what a bad reading-order would produce. Expect left-top,
    left-bottom, right-top, right-bottom after repair."""
    blocks = [
        _block("left-top", 0, y0=10, x0=50, x1=200),
        _block("right-top", 1, y0=10, x0=350, x1=500),
        _block("left-bottom", 2, y0=100, x0=50, x1=200),
        _block("right-bottom", 3, y0=100, x0=350, x1=500),
    ]
    out = repair_two_column_order(blocks)
    assert [b.content for b in out] == [
        "left-top",
        "left-bottom",
        "right-top",
        "right-bottom",
    ]


def test_wide_block_emitted_before_columns() -> None:
    wide = _block("wide-header", 0, y0=5, x0=50, x1=500)
    left = _block("left", 1, y0=50, x0=50, x1=200)
    right = _block("right", 2, y0=50, x0=350, x1=500)
    out = repair_two_column_order([left, right, wide])
    # Wide block comes first (even though input had it last)
    assert out[0].content == "wide-header"
    assert [b.content for b in out[1:]] == ["left", "right"]


def test_multi_page_preserves_page_order() -> None:
    p1_left = _block("p1-left", 0, page=1, y0=10, x0=50, x1=200)
    p1_right = _block("p1-right", 1, page=1, y0=10, x0=350, x1=500)
    p2_left = _block("p2-left", 2, page=2, y0=10, x0=50, x1=200)
    p2_right = _block("p2-right", 3, page=2, y0=10, x0=350, x1=500)
    # Input interleaved
    out = repair_two_column_order([p1_left, p2_left, p1_right, p2_right])
    assert [b.content for b in out] == [
        "p1-left",
        "p1-right",
        "p2-left",
        "p2-right",
    ]


def test_reading_order_is_renumbered() -> None:
    blocks = [
        _block("left", 0, y0=10, x0=50, x1=200),
        _block("right", 1, y0=10, x0=350, x1=500),
    ]
    out = repair_two_column_order(blocks)
    assert [b.reading_order for b in out] == [0, 1]


def test_blocks_without_bbox_kept_with_their_page() -> None:
    normal = _block("positioned", 0, page=1, y0=10, x0=50, x1=200)
    orphan = Block(
        type=BlockType.PARAGRAPH, content="no-bbox", reading_order=1, bbox=None
    )
    out = repair_two_column_order([normal, orphan])
    # No crash; both blocks survive.
    assert len(out) == 2
    contents = {b.content for b in out}
    assert contents == {"positioned", "no-bbox"}


def test_small_page_under_three_blocks_left_alone() -> None:
    left = _block("l", 0, y0=10, x0=50, x1=200)
    right = _block("r", 1, y0=10, x0=350, x1=500)
    # Only 2 blocks on page → repair skips it
    out = repair_two_column_order([left, right])
    assert [b.content for b in out] == ["l", "r"]
