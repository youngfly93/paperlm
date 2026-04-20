"""Unit tests for MarkdownSerializer."""

from markitdown_paperlm.ir import IR, BBox, Block, BlockType
from markitdown_paperlm.serializers.markdown import MarkdownSerializer


def _render(blocks: list[Block]) -> str:
    return MarkdownSerializer().render(IR(blocks=blocks))


def test_empty_ir_renders_empty() -> None:
    assert MarkdownSerializer().render(IR()) == ""


def test_title_and_heading() -> None:
    md = _render([
        Block(type=BlockType.TITLE, content="Paper", reading_order=0),
        Block(type=BlockType.HEADING, content="Intro", attrs={"level": 2}, reading_order=1),
        Block(type=BlockType.PARAGRAPH, content="Hello world.", reading_order=2),
    ])
    assert md == "# Paper\n\n## Intro\n\nHello world.\n"


def test_heading_level_clamped() -> None:
    md = _render([Block(type=BlockType.HEADING, content="Too deep", attrs={"level": 99})])
    assert md.startswith("###### Too deep")

    md = _render([Block(type=BlockType.HEADING, content="Zero", attrs={"level": 0})])
    assert md.startswith("# Zero")


def test_formula_inline_vs_block() -> None:
    md = _render([
        Block(type=BlockType.FORMULA, content="E=mc^2", attrs={"inline": True}),
        Block(type=BlockType.FORMULA, content=r"\int f dx", attrs={"inline": False}),
    ])
    assert "$E=mc^2$" in md
    assert "$$\n\\int f dx\n$$" in md


def test_list_item_ordered_and_unordered() -> None:
    md = _render([
        Block(type=BlockType.LIST_ITEM, content="item1", attrs={"ordered": False}),
        Block(type=BlockType.LIST_ITEM, content="item2", attrs={"ordered": True}),
    ])
    assert "- item1" in md
    assert "1. item2" in md


def test_code_block() -> None:
    md = _render([
        Block(type=BlockType.CODE, content="print('hi')", attrs={"language": "python"})
    ])
    assert "```python\nprint('hi')\n```" in md


def test_reading_order_is_respected() -> None:
    md = _render([
        Block(type=BlockType.PARAGRAPH, content="second", reading_order=1),
        Block(type=BlockType.PARAGRAPH, content="first", reading_order=0),
    ])
    assert md.index("first") < md.index("second")


def test_table_content_passthrough() -> None:
    # DoclingAdapter already renders GFM into block.content; serializer just emits it.
    table_md = "| a | b |\n| - | - |\n| 1 | 2 |"
    md = _render([Block(type=BlockType.TABLE, content=table_md)])
    assert table_md in md


def test_text_cleanup_removes_nulls_ligature_splits_and_dehyphenates() -> None:
    md = _render([
        Block(
            type=BlockType.PARAGRAPH,
            content=(
                "speci fi cally gap- fi lling fi ve fi lters con firm "
                "pro file de finition bu-\nffering\x00"
            ),
        )
    ])

    assert "\x00" not in md
    assert "specifically" in md
    assert "gap-filling" in md
    assert "five filters" in md
    assert "confirm" in md
    assert "profile" in md
    assert "definition" in md
    assert "buffering" in md


def test_short_non_numeric_heading_is_demoted_to_paragraph() -> None:
    md = _render([
        Block(type=BlockType.HEADING, content="a", attrs={"level": 2}, reading_order=0),
        Block(type=BlockType.HEADING, content="1", attrs={"level": 2}, reading_order=1),
    ])

    assert md.startswith("a\n\n## 1")


def test_figure_caption_renders_as_alt_text_without_duplicate_caption() -> None:
    fig = Block(
        type=BlockType.FIGURE,
        content="",
        bbox=BBox(page=1, x0=0, y0=0, x1=100, y1=100),
        reading_order=0,
        attrs={"caption_reading_order": 1},
    )
    cap = Block(
        type=BlockType.CAPTION,
        content="Figure 1. Workflow",
        bbox=BBox(page=1, x0=0, y0=100, x1=100, y1=120),
        reading_order=1,
        attrs={"target_order": 0, "target_type": "figure"},
    )

    md = _render([fig, cap])

    assert md == "![Figure 1. Workflow](figure)\n"
