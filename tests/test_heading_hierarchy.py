from __future__ import annotations

from markitdown_paperlm.ir import Block, BlockType
from markitdown_paperlm.serializers.heading_hierarchy import (
    normalize_and_repair_headings,
)


def _title(text: str, order: int) -> Block:
    return Block(type=BlockType.TITLE, content=text, reading_order=order)


def _heading(text: str, order: int) -> Block:
    return Block(
        type=BlockType.HEADING,
        content=text,
        reading_order=order,
        attrs={"level": 2},
    )


def _para(text: str, order: int) -> Block:
    return Block(type=BlockType.PARAGRAPH, content=text, reading_order=order)


def test_moves_methods_before_late_method_subsections() -> None:
    blocks = [
        _title("Paper", 0),
        _heading("Discussion", 1),
        _para("Discussion body", 2),
        _heading("Inoculation of plant with bacterial suspensions", 3),
        _para("Method body", 4),
        _heading("Plant growth conditions", 5),
        _heading("Methods", 6),
        _heading("Data analysis", 7),
    ]

    out = normalize_and_repair_headings(blocks)
    headings = [block.content for block in out if block.type == BlockType.HEADING]

    assert headings == [
        "Discussion",
        "Methods",
        "Inoculation of plant with bacterial suspensions",
        "Plant growth conditions",
        "Data analysis",
    ]
    assert [block.reading_order for block in out] == list(range(len(out)))


def test_does_not_move_methods_before_previous_main_section() -> None:
    blocks = [
        _title("Paper", 0),
        _heading("Results", 1),
        _heading("Plant growth conditions", 2),
        _heading("Discussion", 3),
        _heading("Methods", 4),
    ]

    out = normalize_and_repair_headings(blocks)
    headings = [block.content for block in out if block.type == BlockType.HEADING]

    assert headings == ["Results", "Plant growth conditions", "Discussion", "Methods"]


def test_normalizes_known_journal_heading_case() -> None:
    blocks = [
        _heading("ReFeReNces aND NOtes", 0),
        _heading("sUPPleMeNtaRY MateRials", 1),
        _heading("acKNOWleDGMeNts", 2),
        _heading("Materials and methods", 3),
    ]

    out = normalize_and_repair_headings(blocks)

    assert [block.content for block in out] == [
        "References and Notes",
        "Supplementary Materials",
        "Acknowledgements",
        "Materials and Methods",
    ]
    assert all(block.type == BlockType.HEADING for block in out)


def test_demotes_journal_furniture_headings() -> None:
    blocks = [
        _heading("ReseaRch aRticle", 0),
        _heading("MICROBIAL ECOLOGY", 1),
        _heading("Article", 2),
        _heading("nature ecology & evolution", 3),
        _heading("Reprints and permissions information is available at", 4),
    ]

    out = normalize_and_repair_headings(blocks)

    assert [block.type for block in out] == [
        BlockType.PARAGRAPH,
        BlockType.PARAGRAPH,
        BlockType.PARAGRAPH,
        BlockType.PARAGRAPH,
        BlockType.PARAGRAPH,
    ]
    assert [block.attrs["demoted_heading_reason"] for block in out] == [
        "journal_furniture",
        "journal_furniture",
        "journal_furniture",
        "journal_furniture",
        "journal_furniture",
    ]


def test_demotes_figure_caption_headings() -> None:
    blocks = [
        _heading("Fig. 7 | Simulations and experimental validations", 0),
        _heading("Figure 2 Experimental overview", 1),
        _heading("Results", 2),
    ]

    out = normalize_and_repair_headings(blocks)

    assert [block.type for block in out] == [
        BlockType.PARAGRAPH,
        BlockType.PARAGRAPH,
        BlockType.HEADING,
    ]
    assert out[0].attrs["demoted_heading_reason"] == "figure_caption_heading"
    assert out[1].attrs["demoted_heading_reason"] == "figure_caption_heading"


def test_demotes_duplicate_title_heading() -> None:
    blocks = [
        _title("Emergent predictability in microbial ecosystems", 0),
        _heading("Emergent predictability in microbial ecosystems", 1),
        _heading("Results", 2),
    ]

    out = normalize_and_repair_headings(blocks)

    assert out[1].type == BlockType.PARAGRAPH
    assert out[1].attrs["demoted_heading_reason"] == "duplicate_title"
    assert out[2].type == BlockType.HEADING
