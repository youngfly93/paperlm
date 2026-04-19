"""Tests for the phase 9 worker-pool probe helpers."""

from __future__ import annotations

from benchmarks.phase9_worker_pool_probe import render_report


def test_render_report_shows_worker_pool_speedup() -> None:
    report = render_report(
        [
            {
                "mode": "fresh-subprocess",
                "status": "ok",
                "elapsed_s": 90.0,
                "peak_mem_mb": 3000.0,
                "rows": [
                    {
                        "fixture": "a.pdf",
                        "status": "ok",
                        "elapsed_s": 30.0,
                        "chars": 100,
                        "blocks": 10,
                        "engine_used": "docling",
                        "first_line": "# A",
                    },
                    {
                        "fixture": "b.pdf",
                        "status": "ok",
                        "elapsed_s": 30.0,
                        "chars": 200,
                        "blocks": 20,
                        "engine_used": "docling",
                        "first_line": "# B",
                    },
                ],
            },
            {
                "mode": "pooled-worker",
                "status": "ok",
                "elapsed_s": 45.0,
                "peak_mem_mb": 3200.0,
                "rows": [
                    {
                        "fixture": "a.pdf",
                        "status": "ok",
                        "elapsed_s": 20.0,
                        "chars": 100,
                        "blocks": 10,
                        "engine_used": "docling",
                        "first_line": "# A",
                    },
                    {
                        "fixture": "b.pdf",
                        "status": "ok",
                        "elapsed_s": 20.0,
                        "chars": 200,
                        "blocks": 20,
                        "engine_used": "docling",
                        "first_line": "# B",
                    },
                ],
            },
        ],
        ["a.pdf", "b.pdf"],
        timeout_s=900,
        max_rss_mb_hard=6144,
    )

    assert "pooled-worker" in report
    assert "`2.00x` faster" in report
    assert "300" in report


def test_render_report_handles_partial_error() -> None:
    report = render_report(
        [
            {
                "mode": "fresh-subprocess",
                "status": "partial_error",
                "elapsed_s": 5.0,
                "peak_mem_mb": "—",
                "rows": [
                    {
                        "fixture": "missing.pdf",
                        "status": "error",
                        "elapsed_s": 0,
                        "chars": 0,
                        "blocks": 0,
                        "engine_used": "failed",
                        "first_line": "",
                        "error": "fixture missing",
                    }
                ],
            }
        ],
        ["missing.pdf"],
        timeout_s=900,
        max_rss_mb_hard=6144,
    )

    assert "fixture missing" in report
    assert "Need both" in report


def test_render_report_includes_recovery_check() -> None:
    report = render_report(
        [
            {
                "mode": "fresh-subprocess",
                "status": "ok",
                "elapsed_s": 20.0,
                "peak_mem_mb": 1000.0,
                "rows": [
                    {
                        "fixture": "a.pdf",
                        "status": "ok",
                        "elapsed_s": 10.0,
                        "chars": 100,
                        "blocks": 10,
                        "engine_used": "docling",
                        "first_line": "# A",
                    }
                ],
            },
            {
                "mode": "pooled-worker",
                "status": "ok",
                "elapsed_s": 10.0,
                "peak_mem_mb": 900.0,
                "rows": [
                    {
                        "fixture": "a.pdf",
                        "status": "ok",
                        "elapsed_s": 10.0,
                        "chars": 100,
                        "blocks": 10,
                        "engine_used": "docling",
                        "first_line": "# A",
                        "worker_index": 0,
                    }
                ],
            },
        ],
        ["a.pdf"],
        recovery_check={
            "fixture": "a.pdf",
            "forced_status": "memory_limit",
            "recovered_status": "ok",
            "recovered_engine": "docling",
            "recovered_chars": 100,
            "recovered_peak_rss_mb": 900.0,
        },
    )

    assert "Recovery Check" in report
    assert "MEMORY_LIMIT" in report
    assert "Recovered peak RSS" in report
