from __future__ import annotations

from markitdown_paperlm.ir import Block, BlockType
from markitdown_paperlm.serializers.numbered_sections import (
    repair_numbered_section_order,
)


def _heading(text: str, order: int) -> Block:
    return Block(
        type=BlockType.HEADING,
        content=text,
        reading_order=order,
        attrs={"level": 2},
    )


def _para(text: str, order: int) -> Block:
    return Block(type=BlockType.PARAGRAPH, content=text, reading_order=order)


def _heading_contents(blocks: list[Block]) -> list[str]:
    return [block.content for block in blocks if block.type == BlockType.HEADING]


def test_moves_parent_heading_before_numbered_children() -> None:
    blocks = [
        _heading("4 Why Self-Attention", 0),
        _heading("5.4 Regularization", 1),
        _heading("5.3 Optimizer", 2),
        _heading("5.2 Hardware and Schedule", 3),
        _heading("5.1 Training Data and Batching", 4),
        _para("This section describes the training regime.", 5),
        _heading("5 Training", 6),
    ]

    out = repair_numbered_section_order(blocks)

    assert _heading_contents(out) == [
        "4 Why Self-Attention",
        "5 Training",
        "5.1 Training Data and Batching",
        "5.2 Hardware and Schedule",
        "5.3 Optimizer",
        "5.4 Regularization",
    ]
    assert [block.reading_order for block in out] == list(range(len(out)))


def test_sorts_consecutive_numeric_sibling_headings() -> None:
    blocks = [
        _heading("3 Model Architecture", 0),
        _heading("3.2 Attention", 1),
        _heading("3.1 Encoder and Decoder Stacks", 2),
        _heading("3.2.2 Multi-Head Attention", 3),
        _heading("3.2.1 Scaled Dot-Product Attention", 4),
    ]

    out = repair_numbered_section_order(blocks)

    assert _heading_contents(out) == [
        "3 Model Architecture",
        "3.1 Encoder and Decoder Stacks",
        "3.2 Attention",
        "3.2.1 Scaled Dot-Product Attention",
        "3.2.2 Multi-Head Attention",
    ]


def test_sorts_local_siblings_separated_by_body_blocks() -> None:
    blocks = [
        _heading("3.1.3 Initial comparison", 0),
        _para("Body for 3.1.3", 1),
        _heading("3.1.2 Using CLIP for zero-shot transfer", 2),
        _para("Body for 3.1.2", 3),
    ]

    out = repair_numbered_section_order(blocks)

    assert _heading_contents(out) == [
        "3.1.2 Using CLIP for zero-shot transfer",
        "3.1.3 Initial comparison",
    ]


def test_moves_late_child_before_following_parent_sibling() -> None:
    blocks = [
        _heading("3.2 Attention", 0),
        _heading("3.3 Position-wise Feed-Forward Networks", 1),
        _heading("3.4 Embeddings and Softmax", 2),
        _heading("3.2.3 Applications of Attention in our Model", 3),
        _heading("4 Why Self-Attention", 4),
        _heading("3.5 Positional Encoding", 5),
    ]

    out = repair_numbered_section_order(blocks)

    assert _heading_contents(out) == [
        "3.2 Attention",
        "3.2.3 Applications of Attention in our Model",
        "3.3 Position-wise Feed-Forward Networks",
        "3.4 Embeddings and Softmax",
        "3.5 Positional Encoding",
        "4 Why Self-Attention",
    ]


def test_sorts_appendix_parent_and_children() -> None:
    blocks = [
        _heading("References", 0),
        _heading("A.2 Models", 1),
        _para("Models body", 2),
        _heading("A.1 Datasets", 3),
        _heading("A Linear-probe evaluation", 4),
    ]

    out = repair_numbered_section_order(blocks)

    assert _heading_contents(out) == [
        "References",
        "A Linear-probe evaluation",
        "A.1 Datasets",
        "A.2 Models",
    ]


def test_sorts_top_level_appendix_letters() -> None:
    blocks = [
        _heading("References", 0),
        _heading("A Linear-probe evaluation", 1),
        _heading("C Duplicate Detector", 2),
        _para("Duplicate detector body", 3),
        _heading("B Zero-Shot Prediction", 4),
        _heading("D Dataset Ablation on YFCC100M", 5),
    ]

    out = repair_numbered_section_order(blocks)

    assert _heading_contents(out) == [
        "References",
        "A Linear-probe evaluation",
        "B Zero-Shot Prediction",
        "C Duplicate Detector",
        "D Dataset Ablation on YFCC100M",
    ]


def test_does_not_move_parent_across_hard_boundary() -> None:
    blocks = [
        _heading("1.1 Background", 0),
        _heading("References", 1),
        _heading("1 Introduction", 2),
    ]

    out = repair_numbered_section_order(blocks)

    assert _heading_contents(out) == [
        "1.1 Background",
        "References",
        "1 Introduction",
    ]
