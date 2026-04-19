"""GFM table rendering and cross-page table merging.

Robust against the kinds of input DoclingAdapter actually produces:
  - Ragged rows (different column counts per row from merged cells)
  - Empty cells (must render with a visible placeholder in GFM)
  - Cells containing pipe ``|`` or newline characters (must be escaped)
  - Wide (CJK) characters that break ``ljust``-based alignment
"""

from __future__ import annotations

import unicodedata


def render_gfm_table(rows: list[list[str]]) -> str:
    """Render a 2D list as a GitHub-flavored Markdown table.

    Empty / ragged inputs return an empty string. The output is always
    a syntactically valid GFM table with a header separator row.

    Args:
        rows: First row is treated as the header. Rows may have different
            lengths — shorter rows are right-padded with empty cells,
            longer rows define the final column count.
    """
    cleaned = _normalize_rows(rows)
    if not cleaned:
        return ""

    n_cols = max(len(r) for r in cleaned)
    if n_cols == 0:
        return ""

    # Pad ragged rows to the max column count.
    padded = [r + [""] * (n_cols - len(r)) for r in cleaned]

    # Compute display widths (CJK-aware) per column.
    widths = [0] * n_cols
    for row in padded:
        for i, cell in enumerate(row):
            w = max(_display_width(cell), 3)  # min 3 so separator always has "---"
            if w > widths[i]:
                widths[i] = w

    def fmt_row(row: list[str]) -> str:
        parts = []
        for i, cell in enumerate(row):
            pad = widths[i] - _display_width(cell)
            parts.append(" " + cell + " " * pad + " ")
        return "|" + "|".join(parts) + "|"

    header = fmt_row(padded[0])
    sep = "|" + "|".join(" " + "-" * w + " " for w in widths) + "|"
    body = [fmt_row(r) for r in padded[1:]]
    return "\n".join([header, sep, *body])


def merge_cross_page_tables(
    blocks: list, *, max_page_gap: int = 1
) -> list:
    """Merge consecutive TABLE blocks split across page boundaries.

    Heuristic: two TABLE blocks merge if
      1. They are directly adjacent in reading order (no intervening blocks
         except CAPTION), and
      2. Their underlying ``attrs['rows']`` have identical column counts, and
      3. Their bbox pages differ by at most ``max_page_gap``.

    The first table keeps its caption; the second table's rows are appended
    (header-dropped if it looks like a repeated header).

    Operates on and returns a new list of Block objects; the input list is
    not mutated.
    """
    from markitdown_paperlm.ir import Block, BlockType

    out: list = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if block.type != BlockType.TABLE or not block.attrs.get("rows"):
            out.append(block)
            i += 1
            continue

        rows: list[list[str]] = list(block.attrs["rows"])
        bbox = block.bbox
        last_page = bbox.page if bbox else None

        # Captions seen between the tables being merged — preserved in output.
        intervening_captions: list = []

        j = i + 1
        while j < len(blocks):
            nxt = blocks[j]
            # Captions are allowed *between* split-table halves; remember them.
            if nxt.type == BlockType.CAPTION:
                intervening_captions.append(nxt)
                j += 1
                continue
            if nxt.type != BlockType.TABLE or not nxt.attrs.get("rows"):
                break

            nxt_rows: list[list[str]] = nxt.attrs["rows"]
            if not rows or not nxt_rows:
                break
            if len(nxt_rows[0]) != len(rows[0]):
                break
            if last_page is not None and nxt.bbox is not None:
                if nxt.bbox.page - last_page > max_page_gap:
                    break

            # Drop a repeated header row if it matches the first table's header
            tail = nxt_rows[1:] if nxt_rows[0] == rows[0] else nxt_rows
            rows.extend(tail)
            if nxt.bbox:
                last_page = nxt.bbox.page
            j += 1

        if j > i + 1:
            merged_md = render_gfm_table(rows)
            merged = Block(
                type=BlockType.TABLE,
                content=merged_md,
                bbox=block.bbox,
                reading_order=block.reading_order,
                attrs={**block.attrs, "rows": rows, "merged_from_pages": True},
            )
            out.append(merged)
            # Re-emit any captions that lived between the merged halves so
            # downstream caption↔table linking (W3D3) can still use them.
            out.extend(intervening_captions)
            i = j
        else:
            out.append(block)
            i += 1

    return out


# ---------- helpers ----------


def _normalize_rows(rows: list[list[str]]) -> list[list[str]]:
    """Drop all-empty rows; escape pipe + newline; blank → ` ` placeholder."""
    out: list[list[str]] = []
    for row in rows or []:
        if not row:
            continue
        cleaned = [_escape_cell(c) for c in row]
        if any(c.strip() for c in cleaned):
            out.append(cleaned)
    return out


def _escape_cell(cell: str | None) -> str:
    if cell is None:
        return " "
    text = str(cell).strip()
    if not text:
        return " "
    # GFM rules: pipes must be escaped; newlines are illegal inside a row.
    text = text.replace("|", r"\|").replace("\r\n", " ").replace("\n", " ")
    return text


def _display_width(text: str) -> int:
    """Column count that a terminal/editor will actually render.

    East-Asian wide characters count as 2 columns; everything else as 1.
    This keeps Chinese tables visually aligned.
    """
    width = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width
