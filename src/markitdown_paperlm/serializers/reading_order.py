"""Two-column reading-order repair.

Docling's Heron layout model usually returns blocks in the correct
reading order for single-column documents, but can still mis-interleave
rows between two-column pages in edge cases: e.g. a caption or side-bar
block that straddles the center gutter gets placed between the two
columns.

Strategy (per page):

  1. Skip pages that have only one visible text column — nothing to fix.
  2. Detect the two-column split by looking at the *gap* in x-coverage
     across block left-edges (``bbox.x0``). If the blocks cluster into
     two groups separated by a measurable horizontal gap, treat it as
     two columns.
  3. Within that page, assign each block to "left", "right", or "wide"
     (spans both columns). Emit wide blocks in their y-order, then the
     entire left column top-to-bottom, then the entire right column.

Blocks without a bbox are treated as wide and kept in their original
position. Blocks on pages that look single-column are untouched.
"""

from __future__ import annotations

from collections import defaultdict

from markitdown_paperlm.ir import Block

# Minimum horizontal gap (in PDF points) between the two column groups
# for us to consider a page to be two-column. ~1 inch.
MIN_COLUMN_GAP = 40.0

# A block is "wide" — i.e. spans both columns — if its width exceeds
# this fraction of the page's content width.
WIDE_BLOCK_RATIO = 0.7


def repair_two_column_order(blocks: list[Block]) -> list[Block]:
    """Return blocks re-ordered to read left-column then right-column per page.

    Single-column pages are preserved exactly. Blocks without bboxes are
    treated as page-wide content and emitted in their original positions.
    Reading-order ``attr`` on the Block is updated to match the new sequence
    so serializers that sort by ``reading_order`` also produce the right
    output.
    """
    if not blocks:
        return blocks

    # Group by page so we can process column layout per page.
    by_page: dict[int | None, list[Block]] = defaultdict(list)
    for block in blocks:
        page = block.bbox.page if block.bbox else None
        by_page[page].append(block)

    # Rebuild the block list page by page, preserving the order of pages
    # as they first appear in the input.
    pages_in_order: list[int | None] = []
    seen: set[int | None] = set()
    for block in blocks:
        page = block.bbox.page if block.bbox else None
        if page not in seen:
            seen.add(page)
            pages_in_order.append(page)

    out: list[Block] = []
    for page in pages_in_order:
        page_blocks = by_page[page]
        if page is None or len(page_blocks) < 3:
            out.extend(page_blocks)
            continue
        out.extend(_repair_page(page_blocks))

    # Re-stamp reading_order so downstream sorters agree.
    for new_idx, block in enumerate(out):
        block.reading_order = new_idx

    return out


def _repair_page(page_blocks: list[Block]) -> list[Block]:
    """Reorder a single page's blocks into left-column, then right-column."""
    bboxes = []
    for block in page_blocks:
        if block.bbox is not None:
            bboxes.append(block.bbox)
    if not bboxes:
        return page_blocks

    # x0 values define column membership.
    x_starts = sorted(bbox.x0 for bbox in bboxes)
    split_x = _two_column_split(x_starts)
    if split_x is None:
        # Single-column page — keep as-is (no change).
        return page_blocks

    # Compute the page's content width so we can flag "wide" blocks.
    min_x = min(bbox.x0 for bbox in bboxes)
    max_x = max(bbox.x1 for bbox in bboxes)
    page_width = max_x - min_x
    wide_threshold = page_width * WIDE_BLOCK_RATIO

    left: list[Block] = []
    right: list[Block] = []
    wide: list[tuple[float, Block]] = []  # (y, block)

    for b in page_blocks:
        if b.bbox is None:
            # Wide by default so we don't drop content.
            wide.append((float("-inf"), b))
            continue
        width = b.bbox.x1 - b.bbox.x0
        if width >= wide_threshold:
            wide.append((b.bbox.y0, b))
            continue
        if b.bbox.x0 < split_x:
            left.append(b)
        else:
            right.append(b)

    left.sort(key=lambda b: b.bbox.y0 if b.bbox else 0.0)
    right.sort(key=lambda b: b.bbox.y0 if b.bbox else 0.0)
    wide.sort(key=lambda pair: pair[0])

    # Emit: wide blocks first (they are usually page headers, titles, or
    # full-width figures/tables whose natural position is above both
    # columns), then left column, then right column.
    return [b for _, b in wide] + left + right


def _two_column_split(x_starts: list[float]) -> float | None:
    """Return the x-position that splits left and right columns, or None.

    Algorithm: look at gaps between consecutive sorted x0 values. If the
    largest gap exceeds MIN_COLUMN_GAP and sits somewhere in the middle
    (i.e. there are blocks both before AND after the gap), treat the
    midpoint of the gap as the column divider.
    """
    if len(x_starts) < 2:
        return None

    best_gap = 0.0
    best_idx = 0
    for i in range(1, len(x_starts)):
        gap = x_starts[i] - x_starts[i - 1]
        if gap > best_gap:
            best_gap = gap
            best_idx = i

    if best_gap < MIN_COLUMN_GAP:
        return None

    # Need at least one block on each side of the gap.
    if best_idx == 0 or best_idx == len(x_starts):
        return None

    left_max = x_starts[best_idx - 1]
    right_min = x_starts[best_idx]
    return (left_max + right_min) / 2.0
