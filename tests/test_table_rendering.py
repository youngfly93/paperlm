"""Tests for serializers.tables — GFM rendering + cross-page merging."""

from __future__ import annotations

from markitdown_paperlm.ir import BBox, Block, BlockType
from markitdown_paperlm.serializers.tables import (
    _display_width,
    _escape_cell,
    merge_cross_page_tables,
    render_gfm_table,
)

# ---------- _display_width ----------


def test_ascii_display_width_is_len() -> None:
    assert _display_width("hello") == 5


def test_cjk_counts_as_two_columns() -> None:
    assert _display_width("生物") == 4
    assert _display_width("生物学") == 6


def test_mixed_width() -> None:
    assert _display_width("abc生物") == 7  # 3 + 4


# ---------- _escape_cell ----------


def test_escape_cell_none_returns_space() -> None:
    assert _escape_cell(None) == " "


def test_escape_cell_empty_string_returns_space() -> None:
    assert _escape_cell("") == " "
    assert _escape_cell("   ") == " "


def test_escape_cell_escapes_pipe() -> None:
    assert _escape_cell("a|b") == r"a\|b"


def test_escape_cell_replaces_newlines() -> None:
    assert _escape_cell("a\nb") == "a b"
    assert _escape_cell("a\r\nb") == "a b"


# ---------- render_gfm_table ----------


def test_empty_rows_returns_empty_string() -> None:
    assert render_gfm_table([]) == ""
    assert render_gfm_table([[]]) == ""
    assert render_gfm_table([["", "", ""]]) == ""  # all-empty row dropped


def test_basic_2col_table() -> None:
    out = render_gfm_table([["a", "b"], ["1", "2"]])
    lines = out.split("\n")
    assert len(lines) == 3  # header, sep, body
    assert lines[0].count("|") == 3
    assert lines[1].strip("| ").replace("|", "").replace(" ", "").strip("-") == ""
    # separator width ≥ 3
    assert "---" in lines[1]


def test_ragged_rows_are_padded() -> None:
    out = render_gfm_table([["a", "b", "c"], ["1"]])
    lines = out.split("\n")
    # body row must have the same number of | as header
    assert lines[0].count("|") == lines[2].count("|")
    assert lines[2].count("|") == 4  # 3 cols → 4 pipes


def test_pipe_escaped_in_output() -> None:
    out = render_gfm_table([["a", "b"], ["x|y", "z"]])
    assert r"x\|y" in out
    # Only the escaped | should survive as content; GFM separators still work
    lines = out.split("\n")
    assert lines[2].count("|") >= 3  # delimiters still present


def test_newlines_stripped() -> None:
    out = render_gfm_table([["a", "b"], ["line\nbreak", "ok"]])
    assert "\nbreak" not in out.split("\n", 2)[2]  # body line shouldn't wrap
    assert "line break" in out


def test_cjk_alignment() -> None:
    """Each row must have the same display-width, not the same string length.

    CJK chars occupy 2 terminal columns but 1 Python-string char, so a
    byte-based check is wrong. We check that the *display width up to each
    pipe* is identical across rows.
    """
    out = render_gfm_table([["列1", "列2"], ["一", "二三"]])
    lines = out.split("\n")

    def pipe_display_positions(line: str) -> list[int]:
        positions = []
        w = 0
        for ch in line:
            if ch == "|":
                positions.append(w)
            w += 2 if _display_width(ch) == 2 else 1
        return positions

    header_pipes = pipe_display_positions(lines[0])
    body_pipes = pipe_display_positions(lines[2])
    assert header_pipes == body_pipes, (
        f"CJK rows must align by display width; got header={header_pipes} "
        f"body={body_pipes}"
    )


def test_empty_cell_gets_visible_space() -> None:
    out = render_gfm_table([["a", "b"], ["", "z"]])
    lines = out.split("\n")
    # The body row must have 3 pipes (2 cols → 3 pipes)
    assert lines[2].count("|") == 3
    # Empty cell should render as at least one space between pipes
    assert "|   " in lines[2] or "| " in lines[2]


def test_min_column_width_for_separator() -> None:
    """Even 1-char cells get `---` separator, per Markdown conventions."""
    out = render_gfm_table([["a"], ["1"]])
    sep = out.split("\n")[1]
    assert "---" in sep


# ---------- merge_cross_page_tables ----------


def _table(rows: list[list[str]], page: int, order: int) -> Block:
    return Block(
        type=BlockType.TABLE,
        content=render_gfm_table(rows),
        bbox=BBox(page=page, x0=0, y0=0, x1=100, y1=100),
        reading_order=order,
        attrs={"rows": rows},
    )


def test_no_tables_passthrough() -> None:
    p = Block(type=BlockType.PARAGRAPH, content="x", reading_order=0)
    out = merge_cross_page_tables([p])
    assert out == [p]


def test_single_table_not_merged() -> None:
    t = _table([["a", "b"], ["1", "2"]], page=3, order=0)
    out = merge_cross_page_tables([t])
    assert len(out) == 1
    assert out[0].attrs.get("merged_from_pages") is not True


def test_two_tables_same_cols_adjacent_pages_merge() -> None:
    t1 = _table([["a", "b"], ["1", "2"]], page=3, order=0)
    t2 = _table([["3", "4"]], page=4, order=1)
    out = merge_cross_page_tables([t1, t2])
    assert len(out) == 1
    assert out[0].attrs.get("merged_from_pages") is True
    assert out[0].attrs["rows"] == [["a", "b"], ["1", "2"], ["3", "4"]]


def test_merge_drops_repeated_header() -> None:
    """When the second table repeats the header, we drop it."""
    t1 = _table([["a", "b"], ["1", "2"]], page=3, order=0)
    t2 = _table([["a", "b"], ["3", "4"]], page=4, order=1)
    out = merge_cross_page_tables([t1, t2])
    assert len(out) == 1
    # "a","b" should appear only once (as header), not twice
    assert out[0].attrs["rows"].count(["a", "b"]) == 1


def test_different_column_counts_do_not_merge() -> None:
    t1 = _table([["a", "b"], ["1", "2"]], page=3, order=0)
    t2 = _table([["x", "y", "z"]], page=4, order=1)
    out = merge_cross_page_tables([t1, t2])
    assert len(out) == 2


def test_page_gap_too_wide_does_not_merge() -> None:
    t1 = _table([["a", "b"], ["1", "2"]], page=3, order=0)
    t2 = _table([["3", "4"]], page=9, order=1)  # gap of 6 pages
    out = merge_cross_page_tables([t1, t2])
    assert len(out) == 2


def test_caption_between_tables_does_not_block_merge() -> None:
    t1 = _table([["a", "b"], ["1", "2"]], page=3, order=0)
    cap = Block(type=BlockType.CAPTION, content="Table 1 (cont.)", reading_order=1)
    t2 = _table([["3", "4"]], page=4, order=2)
    out = merge_cross_page_tables([t1, cap, t2])
    # Caption is still present; tables are merged
    tables = [b for b in out if b.type == BlockType.TABLE]
    captions = [b for b in out if b.type == BlockType.CAPTION]
    assert len(tables) == 1
    assert len(captions) == 1
    assert tables[0].attrs.get("merged_from_pages") is True


def test_intervening_paragraph_blocks_merge() -> None:
    """Random paragraph between tables → treat as distinct tables."""
    t1 = _table([["a", "b"], ["1", "2"]], page=3, order=0)
    p = Block(type=BlockType.PARAGRAPH, content="hello", reading_order=1)
    t2 = _table([["3", "4"]], page=4, order=2)
    out = merge_cross_page_tables([t1, p, t2])
    tables = [b for b in out if b.type == BlockType.TABLE]
    assert len(tables) == 2
