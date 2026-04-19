"""Caption ↔ figure / table pairing.

Docling emits FIGURE / TABLE / CAPTION blocks as a flat stream in reading
order. Our goal is to render each figure/table with its caption directly
below it in the Markdown output.

Strategy (single forward pass over the block list):

  1. Whenever we see a FIGURE or TABLE block, look for the *next*
     CAPTION block within a small window (configurable) on the same
     or neighbouring page. If found, link them via
     ``figure.attrs['caption_id'] = caption_order`` and
     ``caption.attrs['target_order'] = figure_order``.

  2. Look backward similarly if no forward caption is available —
     some journals caption *above* figures.

  3. Unlinked captions are left in reading order as standalone text.

This module purposely only *links* blocks; the serializer still renders
them in reading order. The linker output lets the serializer reorder
captions to sit directly under their target when both blocks are
adjacent or the caption lies before the figure/table.
"""

from __future__ import annotations

from collections.abc import Iterable

from markitdown_paperlm.ir import Block, BlockType

# Max number of blocks between a figure/table and its caption for pairing.
DEFAULT_WINDOW = 3

_TARGETS = (BlockType.FIGURE, BlockType.TABLE)


def link_captions(
    blocks: list[Block], *, window: int = DEFAULT_WINDOW
) -> list[Block]:
    """Annotate caption / figure / table blocks with cross-references.

    Mutates ``attrs`` dicts in place (which are owned per-block) and
    returns the same list for convenience. No blocks are added, removed,
    or reordered here.
    """
    n = len(blocks)
    paired_captions: set[int] = set()

    for i, block in enumerate(blocks):
        if block.type not in _TARGETS:
            continue
        target_page = block.bbox.page if block.bbox else None

        # Forward search first — most scientific journals place captions
        # directly below the figure/table.
        caption_idx = _find_caption(
            blocks,
            start=i + 1,
            stop=min(n, i + 1 + window),
            target_page=target_page,
            used=paired_captions,
        )
        # Fall back to a caption above the element (common for tables).
        if caption_idx is None:
            caption_idx = _find_caption(
                blocks,
                start=max(0, i - window),
                stop=i,
                target_page=target_page,
                used=paired_captions,
                reverse=True,
            )

        if caption_idx is not None:
            caption = blocks[caption_idx]
            caption.attrs["target_order"] = block.reading_order
            caption.attrs["target_type"] = block.type.value
            block.attrs["caption_reading_order"] = caption.reading_order
            paired_captions.add(caption_idx)

    return blocks


def reorder_captions_after_targets(blocks: list[Block]) -> list[Block]:
    """Move each linked CAPTION so it comes right after its target block.

    After this pass, the serializer can just iterate in order and captions
    will render directly beneath their figure / table even when Docling
    originally put them a few paragraphs away.

    Captions not linked to a target are left in their original positions.
    """
    if not blocks:
        return blocks

    # Index captions by reading_order for O(1) lookup.
    captions_by_order: dict[int, Block] = {
        b.reading_order: b
        for b in blocks
        if b.type == BlockType.CAPTION
    }

    # Walk through the input. Whenever we emit a target block, emit the
    # linked caption immediately after it. Then, when we reach the caption
    # in the original stream, skip it — we already placed it.
    emitted_captions: set[int] = set()
    out: list[Block] = []
    for block in blocks:
        if block.type == BlockType.CAPTION and block.reading_order in emitted_captions:
            continue
        out.append(block)
        if block.type in _TARGETS:
            cap_ro = block.attrs.get("caption_reading_order")
            if cap_ro is not None and cap_ro != block.reading_order + 1:
                # Caption is not already adjacent; fetch and append it.
                cap = captions_by_order.get(cap_ro)
                if cap is not None and cap.reading_order not in emitted_captions:
                    out.append(cap)
                    emitted_captions.add(cap.reading_order)

    return out


# ---------- helpers ----------


def _find_caption(
    blocks: list[Block],
    *,
    start: int,
    stop: int,
    target_page: int | None,
    used: set[int],
    reverse: bool = False,
) -> int | None:
    """Return the index of the closest unused CAPTION in blocks[start:stop].

    ``reverse=True`` walks from stop-1 down to start (search above target).
    Caption must be on the same page as the target, or on an adjacent
    page if target_page is known.
    """
    indices: Iterable[int] = (
        range(stop - 1, start - 1, -1) if reverse else range(start, stop)
    )
    for idx in indices:
        if idx in used:
            continue
        cand = blocks[idx]
        if cand.type != BlockType.CAPTION:
            continue
        if target_page is not None and cand.bbox is not None:
            if abs(cand.bbox.page - target_page) > 1:
                continue
        return idx
    return None
