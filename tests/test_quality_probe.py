"""Tests for the phase 6 quality-probe helpers."""

from __future__ import annotations

from benchmarks.phase6_quality_probe import (
    OrderCase,
    ReferenceSnippet,
    evaluate_order,
    normalize_compact,
    score_snippet,
)


def test_normalize_compact_ignores_markdown_hyphens_and_spaces() -> None:
    assert normalize_compact("## Single-cell RNA seq") == "singlecellrnaseq"
    assert normalize_compact("生物 信息学：制造") == "生物信息学制造"


def test_score_snippet_exact_match_uses_compact_text() -> None:
    snippet = ReferenceSnippet(
        fixture="x.pdf",
        role="title",
        text="single-cell spatial RNA-seq",
    )
    result = score_snippet("## Single cell spatial RNA seq", snippet)

    assert result["exact"] is True
    assert result["score"] == 1.0
    assert result["position"] == 0


def test_score_snippet_partial_falls_back_to_token_recall() -> None:
    snippet = ReferenceSnippet(
        fixture="x.pdf",
        role="abstract",
        text="large language models in bioinformatics",
    )
    result = score_snippet("Large language systems are useful.", snippet)

    assert result["exact"] is False
    assert 0 < result["score"] < 1
    assert result["position"] is None


def test_evaluate_order_passes_when_positions_increase() -> None:
    order = evaluate_order(
        "x.pdf",
        [OrderCase("x.pdf", ("title", "abstract", "intro"))],
        [
            {"role": "title", "position": 10},
            {"role": "abstract", "position": 50},
            {"role": "intro", "position": 100},
        ],
    )

    assert order is not None
    assert order["status"] == "pass"


def test_evaluate_order_fails_when_positions_are_reversed() -> None:
    order = evaluate_order(
        "x.pdf",
        [OrderCase("x.pdf", ("title", "abstract", "intro"))],
        [
            {"role": "title", "position": 10},
            {"role": "abstract", "position": 150},
            {"role": "intro", "position": 100},
        ],
    )

    assert order is not None
    assert order["status"] == "fail"


def test_evaluate_order_reports_missing_exact_match() -> None:
    order = evaluate_order(
        "x.pdf",
        [OrderCase("x.pdf", ("title", "abstract"))],
        [
            {"role": "title", "position": 10},
            {"role": "abstract", "position": None},
        ],
    )

    assert order is not None
    assert order["status"] == "missing"
    assert order["missing"] == ["abstract"]
