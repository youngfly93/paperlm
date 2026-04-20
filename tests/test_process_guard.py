"""Tests for benchmark subprocess memory/timeout guardrails."""

from __future__ import annotations

import sys

from benchmarks import process_guard


def test_guarded_subprocess_captures_completed_stdout() -> None:
    result = process_guard.run_guarded_subprocess(
        [sys.executable, "-c", "print('ok')"],
        timeout_s=5,
        max_rss_mb_hard=1024,
        poll_interval_s=0.01,
    )

    assert result.status == "completed"
    assert result.returncode == 0
    assert result.stdout.strip() == "ok"


def test_guarded_subprocess_drains_large_stdout() -> None:
    result = process_guard.run_guarded_subprocess(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 200_000)"],
        timeout_s=5,
        max_rss_mb_hard=1024,
        poll_interval_s=0.01,
    )

    assert result.status == "completed"
    assert result.returncode == 0
    assert len(result.stdout) == 200_000


def test_guarded_subprocess_times_out() -> None:
    result = process_guard.run_guarded_subprocess(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        timeout_s=0.1,
        max_rss_mb_hard=1024,
        poll_interval_s=0.01,
    )

    assert result.status == "timeout"
    assert "timed out" in result.error


def test_guarded_subprocess_enforces_memory_limit(monkeypatch) -> None:
    monkeypatch.setattr(process_guard, "_rss_mb_tree", lambda _pid: 9999.0)

    result = process_guard.run_guarded_subprocess(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        timeout_s=5,
        max_rss_mb_hard=1,
        poll_interval_s=0.01,
    )

    assert result.status == "memory_limit"
    assert result.peak_rss_mb == 9999.0
    assert "RSS hard limit" in result.error
