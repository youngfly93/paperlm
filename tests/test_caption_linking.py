"""Tests for caption ↔ figure/table linking and reorder."""

from __future__ import annotations

from markitdown_paperlm.ir import BBox, Block, BlockType
from markitdown_paperlm.serializers.captions import (
    link_captions,
    reorder_captions_after_targets,
)


def _block(type_: BlockType, text: str, order: int, page: int = 1) -> Block:
    return Block(
        type=type_,
        content=text,
        bbox=BBox(page=page, x0=0, y0=0, x1=100, y1=50),
        reading_order=order,
    )


# ---------- link_captions ----------


def test_empty_list_is_noop() -> None:
    assert link_captions([]) == []


def test_figure_paired_with_following_caption() -> None:
    fig = _block(BlockType.FIGURE, "", 0)
    cap = _block(BlockType.CAPTION, "Figure 1. A diagram.", 1)
    link_captions([fig, cap])

    assert fig.attrs.get("caption_reading_order") == 1
    assert cap.attrs.get("target_order") == 0
    assert cap.attrs.get("target_type") == "figure"


def test_table_paired_with_following_caption() -> None:
    tbl = _block(BlockType.TABLE, "| a |", 5)
    cap = _block(BlockType.CAPTION, "Table 2. Results.", 6)
    link_captions([tbl, cap])

    assert tbl.attrs.get("caption_reading_order") == 6
    assert cap.attrs.get("target_type") == "table"


def test_backward_pairing_when_caption_above() -> None:
    cap = _block(BlockType.CAPTION, "Table 3 caption", 10)
    tbl = _block(BlockType.TABLE, "| x |", 11)
    link_captions([cap, tbl])

    assert tbl.attrs.get("caption_reading_order") == 10
    assert cap.attrs.get("target_order") == 11


def test_forward_search_beats_backward_when_both_present() -> None:
    cap_above = _block(BlockType.CAPTION, "above", 0)
    fig = _block(BlockType.FIGURE, "", 1)
    cap_below = _block(BlockType.CAPTION, "below", 2)
    link_captions([cap_above, fig, cap_below])

    # Forward (below) should win
    assert fig.attrs.get("caption_reading_order") == 2
    assert cap_below.attrs.get("target_order") == 1
    # The one above is left unlinked
    assert "target_order" not in cap_above.attrs


def test_caption_on_distant_page_is_not_paired() -> None:
    fig = _block(BlockType.FIGURE, "", 0, page=3)
    far_cap = _block(BlockType.CAPTION, "Figure 99", 1, page=20)
    link_captions([fig, far_cap])

    assert "caption_reading_order" not in fig.attrs
    assert "target_order" not in far_cap.attrs


def test_each_caption_bound_to_at_most_one_target() -> None:
    fig1 = _block(BlockType.FIGURE, "", 0)
    fig2 = _block(BlockType.FIGURE, "", 1)
    cap = _block(BlockType.CAPTION, "shared?", 2)
    link_captions([fig1, fig2, cap])

    # The cap should pair with fig2 (closer) and not get re-used for fig1.
    # fig1 has no other candidate → remains unlinked.
    linked = {b.attrs.get("caption_reading_order") for b in (fig1, fig2)}
    assert 2 in linked
    assert sum(1 for b in (fig1, fig2) if b.attrs.get("caption_reading_order") == 2) == 1


def test_window_limits_search_range() -> None:
    fig = _block(BlockType.FIGURE, "", 0)
    noise = [_block(BlockType.PARAGRAPH, f"p{i}", i + 1) for i in range(5)]
    cap = _block(BlockType.CAPTION, "Figure 4", 6)
    # Default window = 3 → can't reach caption at position 6
    link_captions([fig, *noise, cap])
    assert "caption_reading_order" not in fig.attrs


# ---------- reorder_captions_after_targets ----------


def test_reorder_moves_caption_right_after_figure() -> None:
    fig = _block(BlockType.FIGURE, "", 0)
    noise = _block(BlockType.PARAGRAPH, "intervening", 1)
    cap = _block(BlockType.CAPTION, "Figure 1", 2)
    tail = _block(BlockType.PARAGRAPH, "after", 3)

    link_captions([fig, noise, cap, tail])
    out = reorder_captions_after_targets([fig, noise, cap, tail])

    types = [b.type for b in out]
    # fig → caption → noise → tail (caption jumps forward, other blocks preserved)
    assert types[0] == BlockType.FIGURE
    assert types[1] == BlockType.CAPTION
    assert types.count(BlockType.CAPTION) == 1  # caption not duplicated


def test_reorder_leaves_unlinked_caption_in_place() -> None:
    cap = _block(BlockType.CAPTION, "orphan", 0)
    p = _block(BlockType.PARAGRAPH, "text", 1)
    out = reorder_captions_after_targets([cap, p])
    assert out[0] is cap
    assert out[1] is p


def test_adjacent_caption_unchanged() -> None:
    fig = _block(BlockType.FIGURE, "", 0)
    cap = _block(BlockType.CAPTION, "Figure 1", 1)
    link_captions([fig, cap])
    out = reorder_captions_after_targets([fig, cap])
    assert [b.reading_order for b in out] == [0, 1]
    assert out.count(cap) == 1
