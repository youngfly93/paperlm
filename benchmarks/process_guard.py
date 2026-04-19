"""Subprocess guardrails for benchmark workers.

The benchmark suite intentionally runs heavy parsers (Docling, PaddleOCR,
Marker, MinerU) in child processes. This module adds the missing hard memory
budget: if a child process tree exceeds the configured RSS limit, the whole
process group is killed and the caller receives a structured result instead
of taking down the parent Python process.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GuardedProcessResult:
    status: str
    returncode: int | None
    stdout: str
    stderr: str
    elapsed_s: float
    peak_rss_mb: float | None
    error: str


def run_guarded_subprocess(
    cmd: list[str],
    *,
    timeout_s: float,
    max_rss_mb_hard: float,
    poll_interval_s: float = 0.25,
) -> GuardedProcessResult:
    """Run a command with wall-clock and RSS limits.

    RSS is sampled for the process tree rooted at the worker PID. This uses
    `ps` / `pgrep` instead of psutil so benchmark scripts stay dependency-free.
    """
    started = time.perf_counter()
    peak_rss_mb: float | None = None
    popen_kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kwargs)
    try:
        while True:
            elapsed_s = time.perf_counter() - started
            current_rss_mb = _rss_mb_tree(proc.pid)
            if current_rss_mb is not None:
                peak_rss_mb = max(peak_rss_mb or 0.0, current_rss_mb)

            if max_rss_mb_hard > 0 and current_rss_mb is not None and current_rss_mb > max_rss_mb_hard:
                _kill_process_tree(proc)
                stdout, stderr = proc.communicate()
                return GuardedProcessResult(
                    status="memory_limit",
                    returncode=proc.returncode,
                    stdout=stdout,
                    stderr=stderr,
                    elapsed_s=round(elapsed_s, 2),
                    peak_rss_mb=round(peak_rss_mb, 1) if peak_rss_mb is not None else None,
                    error=(
                        f"worker exceeded RSS hard limit {max_rss_mb_hard:g} MB "
                        f"(peak {current_rss_mb:.1f} MB)"
                    ),
                )

            returncode = proc.poll()
            if returncode is not None:
                stdout, stderr = proc.communicate()
                return GuardedProcessResult(
                    status="completed",
                    returncode=returncode,
                    stdout=stdout,
                    stderr=stderr,
                    elapsed_s=round(elapsed_s, 2),
                    peak_rss_mb=round(peak_rss_mb, 1) if peak_rss_mb is not None else None,
                    error="",
                )

            if elapsed_s >= timeout_s:
                _kill_process_tree(proc)
                stdout, stderr = proc.communicate()
                return GuardedProcessResult(
                    status="timeout",
                    returncode=proc.returncode,
                    stdout=stdout,
                    stderr=stderr,
                    elapsed_s=round(elapsed_s, 2),
                    peak_rss_mb=round(peak_rss_mb, 1) if peak_rss_mb is not None else None,
                    error=f"worker timed out after {timeout_s:g}s",
                )

            time.sleep(poll_interval_s)
    except Exception:
        _kill_process_tree(proc)
        raise


def _kill_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(proc.pid, signal.SIGKILL)
        else:  # pragma: no cover - Windows fallback
            proc.kill()
    except ProcessLookupError:
        return


def _rss_mb_tree(root_pid: int) -> float | None:
    pids = _process_tree_pids(root_pid)
    rss_kb = 0
    seen = False
    for pid in pids:
        value = _rss_kb(pid)
        if value is None:
            continue
        seen = True
        rss_kb += value
    if not seen:
        return None
    return rss_kb / 1024


def _process_tree_pids(root_pid: int) -> list[int]:
    pids = [root_pid]
    idx = 0
    while idx < len(pids):
        parent = pids[idx]
        idx += 1
        for child in _child_pids(parent):
            if child not in pids:
                pids.append(child)
    return pids


def _child_pids(parent_pid: int) -> list[int]:
    try:
        proc = subprocess.run(
            ["pgrep", "-P", str(parent_pid)],
            capture_output=True,
            text=True,
            check=False,
            timeout=1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode not in (0, 1):
        return []
    pids: list[int] = []
    for line in proc.stdout.splitlines():
        try:
            pids.append(int(line.strip()))
        except ValueError:
            continue
    return pids


def _rss_kb(pid: int) -> int | None:
    try:
        proc = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
            timeout=1,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout.strip()
    if not text:
        return None
    try:
        return int(text.splitlines()[0].strip())
    except ValueError:
        return None
