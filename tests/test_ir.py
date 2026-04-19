"""Unit tests for IR dataclasses and BlockType enum."""

from markitdown_paperlm.ir import IR, BBox, Block, BlockType


def test_block_type_is_string_enum() -> None:
    # Comparison against plain strings should work (useful for serializer dispatch).
    assert BlockType.HEADING == "heading"
    assert BlockType("paragraph") is BlockType.PARAGRAPH


def test_block_defaults() -> None:
    b = Block(type=BlockType.PARAGRAPH, content="hello")
    assert b.bbox is None
    assert b.reading_order == 0
    assert b.attrs == {}


def test_heading_stores_level_in_attrs() -> None:
    b = Block(type=BlockType.HEADING, content="Intro", attrs={"level": 2})
    assert b.attrs["level"] == 2


def test_formula_inline_flag() -> None:
    b = Block(type=BlockType.FORMULA, content=r"E = mc^2", attrs={"inline": True})
    assert b.attrs["inline"] is True


def test_bbox_fields() -> None:
    bb = BBox(page=1, x0=0.0, y0=10.0, x1=100.0, y1=20.0)
    assert bb.page == 1
    assert bb.x1 - bb.x0 == 100.0


def test_ir_defaults_and_len() -> None:
    ir = IR()
    assert len(ir) == 0
    assert ir.engine_used == ""
    assert ir.warnings == []
    assert ir.metadata == {}

    ir.blocks.append(Block(type=BlockType.TITLE, content="Paper"))
    assert len(ir) == 1


def test_ir_supports_warnings() -> None:
    ir = IR(engine_used="docling")
    ir.warnings.append("model download slow")
    assert "slow" in ir.warnings[0]


def test_ir_supports_metadata() -> None:
    ir = IR(engine_used="paddleocr", metadata={"ocr": {"mean_confidence": 0.91}})
    assert ir.metadata["ocr"]["mean_confidence"] == 0.91
