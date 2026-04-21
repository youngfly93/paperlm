"""Conservative repair for numbered scientific section headings.

Two-column ML/arXiv PDFs can emit heading blocks in local inverted order:
``3.2`` before ``3.1``, or children such as ``5.1`` before their parent
``5 Training``. This pass only moves heading blocks with explicit numeric
or appendix-style prefixes. It deliberately does not move arbitrary body
paragraphs, because page-column interleavings can make paragraph ownership
ambiguous without stronger layout evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from markitdown_paperlm.ir import Block, BlockType

_SECTION_PREFIX_RE = re.compile(
    r"^\s*((?:\d+|[A-Z])(?:\.(?:\d+|[A-Z]))*)\.?\s+\S+"
)
_MAX_PARENT_BACKSCAN_BLOCKS = 160
_MAX_REPAIR_PASSES = 24


@dataclass(frozen=True)
class SectionNumber:
    parts: tuple[str, ...]

    @property
    def parent(self) -> tuple[str, ...]:
        return self.parts[:-1]

    def is_child_of(self, other: SectionNumber) -> bool:
        return len(self.parts) > len(other.parts) and self.parts[: len(other.parts)] == other.parts


def repair_numbered_section_order(blocks: list[Block]) -> list[Block]:
    """Repair local inversions among explicitly numbered heading blocks."""
    if not blocks:
        return blocks

    out = list(blocks)
    for _ in range(_MAX_REPAIR_PASSES):
        changed = False
        out, parent_changed = _move_parent_headings_before_children(out)
        changed = changed or parent_changed
        out, late_child_changed = _move_late_children_before_parent_siblings(out)
        changed = changed or late_child_changed
        out, sibling_changed = _move_late_sibling_before_inversion(out)
        changed = changed or sibling_changed
        out, sibling_changed = _sort_consecutive_sibling_headings(out)
        changed = changed or sibling_changed
        if not changed:
            break

    _restamp(out)
    return out


def _move_parent_headings_before_children(blocks: list[Block]) -> tuple[list[Block], bool]:
    out = list(blocks)
    for idx, block in enumerate(out):
        number = _section_number(block)
        if number is None:
            continue

        child_indices = _previous_child_indices(out, idx, number)
        if not child_indices:
            continue

        moving = out.pop(idx)
        insert_at = min(child_indices)
        out.insert(insert_at, moving)
        return out, True

    return out, False


def _previous_child_indices(
    blocks: list[Block],
    parent_index: int,
    parent: SectionNumber,
) -> list[int]:
    scan_start = max(0, parent_index - _MAX_PARENT_BACKSCAN_BLOCKS)
    child_indices: list[int] = []

    for idx in range(parent_index - 1, scan_start - 1, -1):
        block = blocks[idx]
        if block.type != BlockType.HEADING:
            continue
        number = _section_number(block)
        if number is None:
            if _is_hard_boundary_heading(block):
                break
            continue
        if number == parent:
            break
        if number.is_child_of(parent):
            child_indices.append(idx)
            continue
        if len(number.parts) <= len(parent.parts):
            break

    return child_indices


def _move_late_children_before_parent_siblings(
    blocks: list[Block],
) -> tuple[list[Block], bool]:
    out = list(blocks)
    for idx, block in enumerate(out):
        number = _section_number(block)
        if number is None or len(number.parts) < 2:
            continue

        parent = SectionNumber(number.parent)
        ancestor = parent.parent
        parent_key = _section_sort_key(parent)
        insert_candidates: list[int] = []
        scan_start = max(0, idx - _MAX_PARENT_BACKSCAN_BLOCKS)

        for prev_idx in range(idx - 1, scan_start - 1, -1):
            prev_block = out[prev_idx]
            if prev_block.type != BlockType.HEADING:
                continue
            prev_number = _section_number(prev_block)
            if prev_number is None:
                if _is_hard_boundary_heading(prev_block):
                    break
                continue
            if prev_number == parent:
                break
            if len(prev_number.parts) < len(parent.parts):
                break
            if (
                len(prev_number.parts) == len(parent.parts)
                and prev_number.parent == ancestor
                and _section_sort_key(prev_number) > parent_key
            ):
                insert_candidates.append(prev_idx)

        if insert_candidates:
            moving = out.pop(idx)
            out.insert(min(insert_candidates), moving)
            return out, True

    return out, False


def _move_late_sibling_before_inversion(blocks: list[Block]) -> tuple[list[Block], bool]:
    out = list(blocks)
    for idx, block in enumerate(out):
        number = _section_number(block)
        if number is None:
            continue
        if len(number.parts) < 2 and not _is_appendix_letter(number):
            continue

        current_key = _section_sort_key(number)
        insert_candidates: list[int] = []
        scan_start = max(0, idx - _MAX_PARENT_BACKSCAN_BLOCKS)

        for prev_idx in range(idx - 1, scan_start - 1, -1):
            prev_block = out[prev_idx]
            if prev_block.type != BlockType.HEADING:
                continue
            prev_number = _section_number(prev_block)
            if prev_number is None:
                if _is_hard_boundary_heading(prev_block):
                    break
                continue
            if prev_number == SectionNumber(number.parent):
                break
            if len(prev_number.parts) < len(number.parts):
                break
            if prev_number.parent != number.parent:
                continue
            if _section_sort_key(prev_number) > current_key:
                insert_candidates.append(prev_idx)

        if insert_candidates:
            moving = out.pop(idx)
            out.insert(min(insert_candidates), moving)
            return out, True

    return out, False


def _is_appendix_letter(number: SectionNumber) -> bool:
    return len(number.parts) == 1 and len(number.parts[0]) == 1 and number.parts[0].isalpha()


def _sort_consecutive_sibling_headings(blocks: list[Block]) -> tuple[list[Block], bool]:
    out = list(blocks)
    idx = 0
    while idx < len(out):
        number = _section_number(out[idx])
        if number is None:
            idx += 1
            continue

        run_start = idx
        run_numbers = [number]
        idx += 1
        while idx < len(out):
            next_number = _section_number(out[idx])
            if next_number is None or next_number.parent != number.parent:
                break
            run_numbers.append(next_number)
            idx += 1

        run_end = idx
        if len(run_numbers) < 2:
            continue

        sorted_numbers = sorted(run_numbers, key=_section_sort_key)
        if run_numbers == sorted_numbers:
            continue

        run = out[run_start:run_end]
        run.sort(key=lambda block: _section_sort_key(_section_number(block)))
        out[run_start:run_end] = run
        return out, True

    return out, False


def _section_number(block: Block | None) -> SectionNumber | None:
    if block is None or block.type != BlockType.HEADING:
        return None
    match = _SECTION_PREFIX_RE.match(block.content)
    if not match:
        return None
    raw_parts = tuple(part.rstrip(".") for part in match.group(1).split(".") if part)
    if not raw_parts:
        return None
    return SectionNumber(raw_parts)


def _section_sort_key(number: SectionNumber | None) -> tuple[tuple[int, int | str], ...]:
    if number is None:
        return ()
    key: list[tuple[int, int | str]] = []
    for part in number.parts:
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return tuple(key)


def _is_hard_boundary_heading(block: Block) -> bool:
    key = " ".join(block.content.lower().split())
    return key in {
        "abstract",
        "acknowledgements",
        "acknowledgments",
        "references",
        "references and notes",
    }


def _restamp(blocks: list[Block]) -> None:
    for idx, block in enumerate(blocks):
        block.reading_order = idx
