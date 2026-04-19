"""Unit tests for MarkdownSerializer."""

from markitdown_paperlm.ir import IR, Block, BlockType
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
