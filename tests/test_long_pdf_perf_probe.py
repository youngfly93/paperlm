"""Tests for the phase 8 long-PDF performance probe helpers."""

from __future__ import annotations

from benchmarks.phase8_long_pdf_perf_probe import render_report


def test_render_report_includes_breakdown_and_runtime_ratio() -> None:
    report = render_report(
        [
            {
                "tool_key": "docling_standalone",
                "fixture": "sample_arxiv_math.pdf",
                "status": "ok",
                "elapsed_s": 30.0,
                "peak_mem_mb": 1200.0,
                "chars": 1000,
                "formula_markers": 0,
                "first_line": "DeepSeek-R1",
                "meta": {"engine_used": "docling"},
                "timings": {"docling_convert": 29.0, "docling_markdown_export": 1.0},
            },
            {
                "tool_key": "paperlm_breakdown",
                "fixture": "sample_arxiv_math.pdf",
                "status": "ok",
                "elapsed_s": 45.0,
                "peak_mem_mb": 1500.0,
                "chars": 1100,
                "formula_markers": 2,
                "first_line": "# DeepSeek-R1",
                "meta": {"engine_used": "docling", "blocks": 100},
                "timings": {
                    "scanned_check": 1.0,
                    "docling_convert": 40.0,
                    "ir_postprocess": 3.0,
                    "markdown_render": 1.0,
                },
            },
        ],
        timeout_s=600,
    )

    assert "PaperLM Breakdown" in report
    assert "`docling_convert`" in report
    assert "`1.50x` Docling standalone" in report
    assert "CPU profiling: `off`" in report


def test_render_report_handles_no_successful_comparison() -> None:
    report = render_report(
        [
            {
                "tool_key": "paperlm_breakdown",
                "fixture": "missing.pdf",
                "status": "error",
                "elapsed_s": 0,
                "error": "fixture missing",
            }
        ],
        timeout_s=600,
    )

    assert "fixture missing" in report
    assert "Not enough successful rows" in report


def test_render_report_includes_cpu_profile_when_available() -> None:
    report = render_report(
        [
            {
                "tool_key": "paperlm_breakdown",
                "fixture": "sample_arxiv_math.pdf",
                "status": "ok",
                "elapsed_s": 45.0,
                "peak_mem_mb": 1500.0,
                "chars": 1100,
                "formula_markers": 2,
                "first_line": "# DeepSeek-R1",
                "meta": {"engine_used": "docling", "blocks": 100},
                "timings": {"ir_postprocess": 3.0},
                "profile_cumulative": "ncalls  tottime  percall  cumtime  percall filename:lineno(function)\n1 0.1 0.1 3.0 3.0 captions.py:1(link_captions)",
            }
        ],
        timeout_s=600,
        profile_cpu=True,
        profile_top_n=30,
    )

    assert "CPU Profiles" in report
    assert "captions.py" in report
    assert "CPU profiling: `on`" in report
