"""Tests for first-page front-matter normalization."""

from __future__ import annotations

from markitdown_paperlm.ir import BBox, Block, BlockType
from markitdown_paperlm.serializers.front_matter import normalize_front_matter


def _block(
    text: str,
    order: int,
    *,
    type_: BlockType = BlockType.PARAGRAPH,
    page: int = 1,
    x0: float = 50,
    y0: float = 50,
    x1: float = 500,
    y1: float = 70,
) -> Block:
    return Block(
        type=type_,
        content=text,
        reading_order=order,
        bbox=BBox(page=page, x0=x0, y0=y0, x1=x1, y1=y1),
    )


def test_promotes_title_before_affiliation_noise() -> None:
    blocks = [
        _block(
            "1 GenomiqueENS, Institut de Biologie de l'ENS, CNRS, INSERM",
            0,
        ),
        _block(
            "A systematic benchmark of bioinformatics methods for single-cell data",
            1,
            type_=BlockType.HEADING,
            y0=90,
        ),
        _block("Abstract: This paper benchmarks methods.", 2, y0=120),
    ]

    out = normalize_front_matter(blocks)

    assert out[0].content.startswith("A systematic benchmark")
    assert out[0].type == BlockType.TITLE
    assert out[0].attrs["normalized_front_title"] is True
    assert out[-1].content.startswith("1 GenomiqueENS")
    assert [b.reading_order for b in out] == [0, 1, 2]


def test_rejects_author_list_as_title_candidate() -> None:
    blocks = [
        _block(
            ", Parker Glenn 2 , Aditya G. Parameswaran 1 , Madelon Hulsebos 3",
            0,
            type_=BlockType.HEADING,
        ),
        _block(
            "TARGET: Benchmarking Table Retrieval for Generative Tasks",
            1,
            type_=BlockType.HEADING,
            y0=90,
        ),
        _block("Abstract: Table retrieval is difficult.", 2, y0=120),
    ]

    out = normalize_front_matter(blocks)

    assert out[0].content == "TARGET: Benchmarking Table Retrieval for Generative Tasks"
    assert out[0].type == BlockType.TITLE
    assert out[-1].content.startswith(", Parker Glenn")


def test_preserves_blocks_when_no_plausible_title_exists() -> None:
    blocks = [
        _block("Abstract: This starts with the abstract.", 0),
        _block("Keywords: parser, markdown", 1, y0=90),
    ]

    out = normalize_front_matter(blocks)

    assert out is blocks
    assert [b.content for b in out] == [
        "Abstract: This starts with the abstract.",
        "Keywords: parser, markdown",
    ]


def test_only_first_page_is_reordered() -> None:
    p1_aff = _block("University of Example, Department of Biology", 0)
    p1_title = _block("Large Language Models in Bioinformatics: A Survey", 1, type_=BlockType.HEADING)
    p2 = _block("Second page starts here.", 2, page=2)

    out = normalize_front_matter([p1_aff, p1_title, p2])

    assert [b.content for b in out] == [
        "Large Language Models in Bioinformatics: A Survey",
        "University of Example, Department of Biology",
        "Second page starts here.",
    ]
