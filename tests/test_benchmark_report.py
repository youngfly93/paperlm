"""Tests for the unified release-facing benchmark report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch

from benchmarks import benchmark_report


def _ok_row(tool_key: str, fixture: str, *, elapsed_s: float = 1.0) -> dict[str, Any]:
    return {
        "tool_key": tool_key,
        "fixture": fixture,
        "status": "ok",
        "elapsed_s": elapsed_s,
        "peak_rss_mb": 100.0,
        "chars": 1000,
        "lines": 50,
        "headings": 5,
        "tables": 0,
        "formula_markers": 0,
        "cid_tokens": 0,
        "first_line": "# Example Title",
        "first_line_title_like": True,
        "engine_used": "fake",
        "warnings": [],
        "ocr_mean_confidence": None,
        "ocr_low_confidence_pages": [],
        "snippet_total": 1,
        "snippet_exact_hits": 1,
        "snippet_avg_score": 1.0,
        "snippet_results": [{"role": "title", "exact": True, "score": 1.0, "position": 0}],
        "order": {"status": "pass", "roles": ("title",), "missing": [], "positions": {"title": 0}},
        "error": "",
    }


def test_select_fixture_names_profiles() -> None:
    full = benchmark_report.select_fixture_names("full")
    quality = benchmark_report.select_fixture_names("quality")

    assert len(full) == 8
    assert "sample_arxiv_math.pdf" in full
    assert quality == list(benchmark_report.phase6.DEFAULT_FIXTURES)


def test_parse_tools_rejects_unknown() -> None:
    try:
        benchmark_report.parse_tools("paperlm_plugin,missing_tool")
    except ValueError as exc:
        assert "missing_tool" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError")


def test_build_report_writes_markdown_and_json(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_collect_one(
        tool_key: str,
        fixture_name: str,
        *,
        timeout_s: float,
        max_rss_mb_hard: float,
    ) -> dict[str, Any]:
        return _ok_row(tool_key, fixture_name, elapsed_s=timeout_s / 100)

    monkeypatch.setattr(benchmark_report, "_collect_one", fake_collect_one)
    monkeypatch.setattr(benchmark_report, "is_tool_available", lambda _tool: True)

    report = benchmark_report.build_report(
        ["paperlm_plugin", "docling_standalone"],
        ["sample_en_two_col.pdf"],
        profile="custom",
        timeout_s=10,
        generated_at="2026-04-19T00:00:00+00:00",
    )
    md_path, json_path = benchmark_report.write_outputs(report, tmp_path)

    markdown = md_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert "Executive Summary" in markdown
    assert "Tool Summary" in markdown
    assert "Quality Matrix" in markdown
    assert payload["schema_version"] == 1
    assert payload["profile"] == "custom"
    assert payload["summary"]["tools"]["paperlm_plugin"]["successful_runs"] == 1
    assert payload["results"][0]["fixture"] == "sample_en_two_col.pdf"


def test_collect_guardrails_reports_memory_empty_and_slowdown() -> None:
    rows = [
        _ok_row("paperlm_plugin", "sample_en_two_col.pdf", elapsed_s=31.0),
        _ok_row("docling_standalone", "sample_en_two_col.pdf", elapsed_s=10.0),
        {
            **_ok_row("paperlm_plugin", "sample_zh_mixed.pdf"),
            "peak_rss_mb": 5000.0,
        },
        {
            "tool_key": "markitdown_baseline",
            "fixture": "sample_scanned_1p.pdf",
            "status": "empty",
            "elapsed_s": 0.5,
            "error": "empty markdown",
        },
    ]

    guardrails = benchmark_report.collect_guardrails(rows, max_rss_mb=4096)
    kinds = {row["kind"] for row in guardrails}

    assert "latency" in kinds
    assert "rss" in kinds
    assert "empty" in kinds
