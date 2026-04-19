"""Tests for phase 5 benchmark guardrails."""

from __future__ import annotations

from typing import Any

from benchmarks import phase5_competitor_compare as phase5
from benchmarks.process_guard import GuardedProcessResult


def test_select_fixture_names_defaults_to_smoke_profile() -> None:
    fixtures = phase5.select_fixture_names("smoke")

    assert fixtures == [
        "sample_arxiv_table_heavy.pdf",
        "sample_zh_mixed.pdf",
        "sample_scanned_1p.pdf",
    ]
    assert "sample_scanned.pdf" not in fixtures
    assert "sample_arxiv_long_ir.pdf" not in fixtures


def test_select_fixture_names_allows_custom_fixture_override() -> None:
    fixtures = phase5.select_fixture_names("smoke", "sample_en_two_col.pdf,sample_scanned_1p.pdf")

    assert fixtures == ["sample_en_two_col.pdf", "sample_scanned_1p.pdf"]


def test_render_performance_guardrails_reports_timeout_rss_and_slowdown() -> None:
    report = "\n".join(
        phase5._render_performance_guardrails(
            [
                {
                    "tool_key": "paperlm_plugin",
                    "fixture": "sample_arxiv_math.pdf",
                    "status": "ok",
                    "elapsed_s": 31.0,
                    "peak_mem_mb": 5000,
                },
                {
                    "tool_key": "docling_standalone",
                    "fixture": "sample_arxiv_math.pdf",
                    "status": "ok",
                    "elapsed_s": 10.0,
                    "peak_mem_mb": 1000,
                },
                {
                    "tool_key": "paperlm_plugin",
                    "fixture": "sample_scanned_1p.pdf",
                    "status": "timeout",
                    "elapsed_s": 240.0,
                    "error": "worker timed out after 240s",
                },
            ],
            max_rss_mb=4096,
        )
    )

    assert "timeout" in report
    assert "peak RSS 5000.0 MB" in report
    assert ">3x Docling standalone" in report


def test_run_one_returns_timeout_result(monkeypatch: Any) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> GuardedProcessResult:
        return GuardedProcessResult(
            status="timeout",
            returncode=None,
            stdout="",
            stderr="model init stalled",
            elapsed_s=1,
            peak_rss_mb=123.4,
            error="worker timed out after 1s",
        )

    monkeypatch.setattr(phase5, "run_guarded_subprocess", fake_run)

    result = phase5._run_one(
        "paperlm_plugin",
        "sample_scanned_1p.pdf",
        timeout_s=1,
    )

    assert result["status"] == "timeout"
    assert result["elapsed_s"] == 1
    assert result["peak_mem_mb"] == 123.4
    assert "model init stalled" in result["error"]


def test_run_one_returns_memory_limit_result(monkeypatch: Any) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> GuardedProcessResult:
        return GuardedProcessResult(
            status="memory_limit",
            returncode=None,
            stdout="",
            stderr="",
            elapsed_s=2,
            peak_rss_mb=7000.0,
            error="worker exceeded RSS hard limit 6144 MB (peak 7000.0 MB)",
        )

    monkeypatch.setattr(phase5, "run_guarded_subprocess", fake_run)

    result = phase5._run_one(
        "paperlm_plugin",
        "sample_scanned_1p.pdf",
        timeout_s=10,
        max_rss_mb_hard=6144,
    )

    assert result["status"] == "memory_limit"
    assert result["peak_mem_mb"] == 7000.0
    assert "RSS hard limit" in result["error"]
