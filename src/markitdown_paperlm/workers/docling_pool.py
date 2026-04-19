"""Long-lived worker pool for server/batch PDF conversion.

The normal MarkItDown API is ideal for single conversions. Batch ingestion has
different constraints: avoid repeated Docling cold starts, keep heavy models out
of the parent process, and kill only the offending worker when a task exceeds a
timeout or RSS budget.
"""

from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any


@dataclass
class WorkerPoolResult:
    """Structured result returned by :class:`DoclingWorkerPool`."""

    status: str
    pdf_path: str
    elapsed_s: float
    markdown: str = ""
    engine_used: str = ""
    warnings: list[str] = field(default_factory=list)
    paperlm_dict: dict[str, Any] | None = None
    paperlm_chunks_jsonl: str = ""
    error: str = ""
    worker_index: int = 0
    peak_rss_mb: float | None = None


class DoclingWorkerPool:
    """Pool of reusable paperlm workers.

    Each worker is a separate Python subprocess that keeps a MarkItDown instance
    alive. The pool process never imports Docling/PaddleOCR directly.
    """

    def __init__(
        self,
        *,
        num_workers: int = 1,
        timeout_s: float = 300.0,
        max_rss_mb_hard: float = 6144.0,
        engine: str = "docling",
        enable_ocr: bool = False,
        enable_formula: bool = False,
        python_executable: str = sys.executable,
        worker_command: list[str] | None = None,
        poll_interval_s: float = 0.1,
    ) -> None:
        if num_workers < 1:
            raise ValueError("num_workers must be >= 1")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be > 0")
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be > 0")

        self.num_workers = num_workers
        self.timeout_s = timeout_s
        self.max_rss_mb_hard = max_rss_mb_hard
        self.engine = engine
        self.enable_ocr = enable_ocr
        self.enable_formula = enable_formula
        self.python_executable = python_executable
        self.worker_command = worker_command
        self.poll_interval_s = poll_interval_s

        self._workers: list[_WorkerProcess] = []
        self._next_worker = 0
        self._lock = threading.Lock()

    def __enter__(self) -> DoclingWorkerPool:
        return self.start()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def start(self) -> DoclingWorkerPool:
        with self._lock:
            if self._workers:
                return self
            self._workers = [_WorkerProcess(self, idx) for idx in range(self.num_workers)]

        for worker in self._workers:
            worker.start()
        return self

    def close(self) -> None:
        with self._lock:
            workers = self._workers
            self._workers = []
            self._next_worker = 0

        for worker in workers:
            worker.close()

    def convert(self, pdf_path: str | os.PathLike[str]) -> WorkerPoolResult:
        path = Path(pdf_path)
        if not path.exists():
            return WorkerPoolResult(
                status="error",
                pdf_path=str(path),
                elapsed_s=0.0,
                engine_used="failed",
                error=f"PDF not found: {path}",
            )

        self.start()
        return self._pick_worker().convert(path)

    def convert_many(self, pdf_paths: Sequence[str | os.PathLike[str]]) -> list[WorkerPoolResult]:
        if not pdf_paths:
            return []
        self.start()
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            return list(executor.map(self.convert, pdf_paths))

    def _command(self) -> list[str]:
        if self.worker_command is not None:
            return list(self.worker_command)

        cmd = [
            self.python_executable,
            "-m",
            "markitdown_paperlm.workers.docling_worker",
            "--engine",
            self.engine,
        ]
        if self.enable_ocr:
            cmd.append("--enable-ocr")
        if self.enable_formula:
            cmd.append("--enable-formula")
        return cmd

    def _pick_worker(self) -> _WorkerProcess:
        with self._lock:
            if not self._workers:
                raise RuntimeError("DoclingWorkerPool is closed")
            worker = self._workers[self._next_worker % len(self._workers)]
            self._next_worker += 1
            return worker


class _WorkerProcess:
    def __init__(self, pool: DoclingWorkerPool, index: int) -> None:
        self.pool = pool
        self.index = index
        self._proc: subprocess.Popen[str] | None = None
        self._stderr_file: IO[str] | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return

        stderr_file = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
        popen_kwargs: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": stderr_file,
            "text": True,
            "bufsize": 1,
        }
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True

        self._stderr_file = stderr_file
        self._proc = subprocess.Popen(self.pool._command(), **popen_kwargs)

    def close(self) -> None:
        with self._lock:
            self._stop(graceful=True)

    def convert(self, pdf_path: Path) -> WorkerPoolResult:
        with self._lock:
            started = time.perf_counter()
            self.start()
            proc = self._require_proc()
            request_id = uuid.uuid4().hex
            request = {"id": request_id, "pdf_path": str(pdf_path)}

            try:
                stdin = self._require_stdin(proc)
                stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
                stdin.flush()
            except OSError as exc:
                error = self._error_with_stderr(f"worker write failed: {exc}")
                self._restart()
                return WorkerPoolResult(
                    status="error",
                    pdf_path=str(pdf_path),
                    elapsed_s=round(time.perf_counter() - started, 3),
                    engine_used="failed",
                    error=error,
                    worker_index=self.index,
                )

            return self._read_response(request_id, pdf_path, started)

    def _read_response(
        self,
        request_id: str,
        pdf_path: Path,
        started: float,
    ) -> WorkerPoolResult:
        peak_rss_mb: float | None = None

        while True:
            proc = self._require_proc()
            elapsed_s = time.perf_counter() - started
            current_rss_mb = _rss_mb_tree(proc.pid)
            if current_rss_mb is not None:
                peak_rss_mb = max(peak_rss_mb or 0.0, current_rss_mb)

            if (
                self.pool.max_rss_mb_hard > 0
                and current_rss_mb is not None
                and current_rss_mb > self.pool.max_rss_mb_hard
            ):
                peak_value = peak_rss_mb if peak_rss_mb is not None else current_rss_mb
                self._restart()
                return WorkerPoolResult(
                    status="memory_limit",
                    pdf_path=str(pdf_path),
                    elapsed_s=round(elapsed_s, 3),
                    engine_used="failed",
                    error=(
                        f"worker exceeded RSS hard limit {self.pool.max_rss_mb_hard:g} MB "
                        f"(peak {current_rss_mb:.1f} MB)"
                    ),
                    worker_index=self.index,
                    peak_rss_mb=round(peak_value, 1),
                )

            if elapsed_s >= self.pool.timeout_s:
                self._restart()
                return WorkerPoolResult(
                    status="timeout",
                    pdf_path=str(pdf_path),
                    elapsed_s=round(elapsed_s, 3),
                    engine_used="failed",
                    error=f"worker timed out after {self.pool.timeout_s:g}s",
                    worker_index=self.index,
                    peak_rss_mb=round(peak_rss_mb, 1) if peak_rss_mb is not None else None,
                )

            if proc.poll() is not None:
                error = self._error_with_stderr(f"worker exited with code {proc.returncode}")
                self._restart()
                return WorkerPoolResult(
                    status="error",
                    pdf_path=str(pdf_path),
                    elapsed_s=round(elapsed_s, 3),
                    engine_used="failed",
                    error=error,
                    worker_index=self.index,
                    peak_rss_mb=round(peak_rss_mb, 1) if peak_rss_mb is not None else None,
                )

            line = self._readline_if_ready(proc)
            if line is None:
                continue
            if not line.strip():
                continue

            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                error = self._error_with_stderr(f"worker emitted invalid JSON: {exc}")
                self._restart()
                return WorkerPoolResult(
                    status="error",
                    pdf_path=str(pdf_path),
                    elapsed_s=round(time.perf_counter() - started, 3),
                    engine_used="failed",
                    error=error,
                    worker_index=self.index,
                    peak_rss_mb=round(peak_rss_mb, 1) if peak_rss_mb is not None else None,
                )

            if payload.get("id") != request_id:
                error = self._error_with_stderr(
                    f"worker protocol desync: expected id {request_id}, got {payload.get('id')}"
                )
                self._restart()
                return WorkerPoolResult(
                    status="error",
                    pdf_path=str(pdf_path),
                    elapsed_s=round(time.perf_counter() - started, 3),
                    engine_used="failed",
                    error=error,
                    worker_index=self.index,
                    peak_rss_mb=round(peak_rss_mb, 1) if peak_rss_mb is not None else None,
                )

            return _result_from_payload(
                payload,
                fallback_pdf_path=str(pdf_path),
                worker_index=self.index,
                peak_rss_mb=round(peak_rss_mb, 1) if peak_rss_mb is not None else None,
            )

    def _readline_if_ready(self, proc: subprocess.Popen[str]) -> str | None:
        stdout = self._require_stdout(proc)
        ready, _, _ = select.select([stdout.fileno()], [], [], self.pool.poll_interval_s)
        if not ready:
            return None
        return stdout.readline()

    def _restart(self) -> None:
        self._stop(graceful=False)
        self.start()

    def _stop(self, *, graceful: bool) -> None:
        proc = self._proc
        if proc is None:
            self._close_stderr()
            return

        if proc.poll() is None and graceful:
            try:
                stdin = self._require_stdin(proc)
                stdin.write(json.dumps({"id": "shutdown", "cmd": "shutdown"}) + "\n")
                stdin.flush()
                proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                _kill_process_tree(proc)

        if proc.poll() is None:
            _kill_process_tree(proc)

        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:  # pragma: no cover - SIGKILL should finish
            pass

        for stream in (proc.stdin, proc.stdout):
            if stream is not None:
                stream.close()
        self._proc = None
        self._close_stderr()

    def _error_with_stderr(self, message: str) -> str:
        stderr = self._stderr_tail()
        if stderr:
            return f"{message}; stderr: {stderr}"
        return message

    def _stderr_tail(self, limit: int = 4000) -> str:
        stderr_file = self._stderr_file
        if stderr_file is None:
            return ""
        try:
            stderr_file.flush()
            pos = stderr_file.tell()
            stderr_file.seek(0)
            data = stderr_file.read()
            stderr_file.seek(pos)
        except OSError:
            return ""
        return data[-limit:].strip()

    def _close_stderr(self) -> None:
        if self._stderr_file is not None:
            self._stderr_file.close()
            self._stderr_file = None

    def _require_proc(self) -> subprocess.Popen[str]:
        if self._proc is None:
            raise RuntimeError("worker process is not started")
        return self._proc

    @staticmethod
    def _require_stdin(proc: subprocess.Popen[str]) -> IO[str]:
        if proc.stdin is None:
            raise RuntimeError("worker stdin is not available")
        return proc.stdin

    @staticmethod
    def _require_stdout(proc: subprocess.Popen[str]) -> IO[str]:
        if proc.stdout is None:
            raise RuntimeError("worker stdout is not available")
        return proc.stdout


def _result_from_payload(
    payload: dict[str, Any],
    *,
    fallback_pdf_path: str,
    worker_index: int,
    peak_rss_mb: float | None,
) -> WorkerPoolResult:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list):
        warnings = []

    paperlm_dict = payload.get("paperlm_dict")
    if not isinstance(paperlm_dict, dict):
        paperlm_dict = None

    return WorkerPoolResult(
        status=str(payload.get("status") or "error"),
        pdf_path=str(payload.get("pdf_path") or fallback_pdf_path),
        elapsed_s=_float_value(payload.get("elapsed_s")),
        markdown=str(payload.get("markdown") or ""),
        engine_used=str(payload.get("engine_used") or ""),
        warnings=[str(item) for item in warnings],
        paperlm_dict=paperlm_dict,
        paperlm_chunks_jsonl=str(payload.get("paperlm_chunks_jsonl") or ""),
        error=str(payload.get("error") or ""),
        worker_index=worker_index,
        peak_rss_mb=peak_rss_mb,
    )


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
