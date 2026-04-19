"""Phase 9 worker-pool probe.

Commercial batch ingestion is often many medium PDFs, not one huge PDF. This
probe compares two safe execution models using the production
``DoclingWorkerPool`` API:

1. fresh-subprocess: create one guarded pool/worker per PDF
2. pooled-worker: reuse long-lived guarded worker(s) for the whole batch

Both paths use the same per-task timeout and hard RSS limit. The parent
benchmark process never imports Docling/PaddleOCR; heavy conversion stays in
worker subprocesses.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parent
SRC = ROOT / "src"
FIX = ROOT / "tests" / "fixtures"
REPORT = HERE / "phase9_worker_pool_report.md"
DEFAULT_FIXTURES = (
    "sample_arxiv_table_heavy.pdf",
    "sample_zh_mixed.pdf",
    "sample_arxiv_llm_survey.pdf",
)
DEFAULT_TIMEOUT_S = 900.0
DEFAULT_MAX_RSS_MB_HARD = 6144.0
DEFAULT_POOL_WORKERS = 1

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

_pythonpath = os.environ.get("PYTHONPATH", "")
if str(SRC) not in _pythonpath.split(os.pathsep):
    os.environ["PYTHONPATH"] = str(SRC) + (os.pathsep + _pythonpath if _pythonpath else "")

from markitdown_paperlm.workers import DoclingWorkerPool, WorkerPoolResult  # noqa: E402


def run_probe(
    fixtures: list[str],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
    pool_workers: int = DEFAULT_POOL_WORKERS,
) -> list[dict[str, Any]]:
    return [
        run_fresh_subprocesses(
            fixtures,
            timeout_s=timeout_s,
            max_rss_mb_hard=max_rss_mb_hard,
        ),
        run_pooled_worker(
            fixtures,
            timeout_s=timeout_s,
            max_rss_mb_hard=max_rss_mb_hard,
            pool_workers=pool_workers,
        ),
    ]


def run_fresh_subprocesses(
    fixtures: list[str],
    *,
    timeout_s: float,
    max_rss_mb_hard: float,
) -> dict[str, Any]:
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        path = FIX / fixture
        if not path.exists():
            rows.append(_missing_row(fixture))
            continue

        with DoclingWorkerPool(
            num_workers=1,
            timeout_s=timeout_s,
            max_rss_mb_hard=max_rss_mb_hard,
            engine="docling",
            enable_ocr=False,
            enable_formula=False,
        ) as pool:
            rows.append(_row_from_result(pool.convert(path), fixture))

    return {
        "mode": "fresh-subprocess",
        "status": _status_from_rows(rows),
        "elapsed_s": round(time.perf_counter() - started, 2),
        "peak_mem_mb": _max_peak(rows),
        "rows": rows,
    }


def run_pooled_worker(
    fixtures: list[str],
    *,
    timeout_s: float,
    max_rss_mb_hard: float,
    pool_workers: int = DEFAULT_POOL_WORKERS,
) -> dict[str, Any]:
    started = time.perf_counter()
    resolved: list[tuple[str, Path | None]] = [
        (fixture, FIX / fixture if (FIX / fixture).exists() else None) for fixture in fixtures
    ]
    existing_paths = [path for _, path in resolved if path is not None]
    converted: list[WorkerPoolResult] = []

    if existing_paths:
        with DoclingWorkerPool(
            num_workers=pool_workers,
            timeout_s=timeout_s,
            max_rss_mb_hard=max_rss_mb_hard,
            engine="docling",
            enable_ocr=False,
            enable_formula=False,
        ) as pool:
            converted = pool.convert_many(existing_paths)

    result_iter = iter(converted)
    rows: list[dict[str, Any]] = []
    for fixture, path in resolved:
        if path is None:
            rows.append(_missing_row(fixture))
        else:
            rows.append(_row_from_result(next(result_iter), fixture))

    return {
        "mode": "pooled-worker",
        "status": _status_from_rows(rows),
        "elapsed_s": round(time.perf_counter() - started, 2),
        "peak_mem_mb": _max_peak(rows),
        "rows": rows,
        "pool_workers": pool_workers,
    }


def render_report(
    results: list[dict[str, Any]],
    fixtures: list[str],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
    pool_workers: int = DEFAULT_POOL_WORKERS,
    recovery_check: dict[str, Any] | None = None,
) -> str:
    lines = [
        "# Phase 9 - Worker Pool Probe",
        "",
        "Batch-ingestion probe comparing one fresh worker per PDF vs reusable `DoclingWorkerPool` workers for the whole batch.",
        "",
        f"Fixtures: {', '.join(f'`{fixture}`' for fixture in fixtures)}.",
        f"Timeout: `{timeout_s:g}s`; RSS hard-kill threshold: `{max_rss_mb_hard:g} MB`; pooled workers: `{pool_workers}`.",
        "",
        "## Summary",
        "",
        "| Mode | Status | OK docs | Total time (s) | Peak RSS (MB) | Median doc time (s) | Total chars | First issue |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for result in results:
        rows = result.get("rows", [])
        ok_rows = [row for row in rows if row.get("status") == "ok"]
        med_doc_time = (
            round(statistics.median(float(row["elapsed_s"]) for row in ok_rows), 2)
            if ok_rows
            else "—"
        )
        issue = next((row.get("error", "") for row in rows if row.get("status") != "ok"), "")
        lines.append(
            f"| {result.get('mode', 'unknown')} | {str(result.get('status', 'unknown')).upper()} | "
            f"{len(ok_rows)}/{len(rows)} | {result.get('elapsed_s', '—')} | "
            f"{result.get('peak_mem_mb', '—')} | {med_doc_time} | "
            f"{sum(int(row.get('chars', 0)) for row in ok_rows)} | `{_compact(issue)[:100]}` |"
        )

    lines.extend(["", "## Details", ""])
    lines.extend(
        [
            "| Mode | Fixture | Status | Worker | Time (s) | Peak RSS (MB) | Chars | Blocks | Engine | First line / error |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for result in results:
        mode = str(result.get("mode", "unknown"))
        for row in result.get("rows", []):
            detail = row.get("first_line") if row.get("status") == "ok" else row.get("error", "")
            lines.append(
                f"| {mode} | `{row.get('fixture', '—')}` | {str(row.get('status', 'unknown')).upper()} | "
                f"{row.get('worker_index', '—')} | {row.get('elapsed_s', '—')} | "
                f"{row.get('peak_rss_mb', '—')} | {row.get('chars', '—')} | "
                f"{row.get('blocks', '—')} | {row.get('engine_used', '—')} | `{_compact(str(detail))[:120]}` |"
            )

    if recovery_check is not None:
        lines.extend(_render_recovery_check(recovery_check))

    lines.extend(_render_observations(results, pool_workers=pool_workers))
    return "\n".join(lines).rstrip() + "\n"


def _render_observations(
    results: list[dict[str, Any]],
    *,
    pool_workers: int = DEFAULT_POOL_WORKERS,
) -> list[str]:
    by_mode = {result.get("mode"): result for result in results}
    fresh = by_mode.get("fresh-subprocess")
    pooled = by_mode.get("pooled-worker")
    lines = ["", "## Observations", ""]
    if not fresh or not pooled:
        lines.append("- Need both fresh-subprocess and pooled-worker rows to compare throughput.")
        return lines

    fresh_time = _to_float(fresh.get("elapsed_s"))
    pooled_time = _to_float(pooled.get("elapsed_s"))
    if fresh_time and pooled_time:
        speedup = fresh_time / pooled_time
        direction = "faster" if speedup >= 1 else "slower"
        lines.append(
            f"- The pooled worker was `{abs(speedup):.2f}x` {direction} than fresh subprocesses "
            f"({pooled_time:.2f}s vs {fresh_time:.2f}s)."
        )
    fresh_peak = _to_float(fresh.get("peak_mem_mb"))
    pooled_peak = _to_float(pooled.get("peak_mem_mb"))
    if fresh_peak and pooled_peak:
        lines.append(
            f"- Peak RSS was `{pooled_peak:.1f} MB` for pooled-worker vs `{fresh_peak:.1f} MB` per fresh worker."
        )
    pooled_rows = pooled.get("rows", [])
    pooled_indices = sorted(
        {
            int(row["worker_index"])
            for row in pooled_rows
            if isinstance(row.get("worker_index"), int) and row.get("status") == "ok"
        }
    )
    if pooled_indices:
        lines.append(
            f"- Pooled worker indices observed: `{pooled_indices}` across `{len(pooled_rows)}` docs, "
            "which is the reuse evidence to check when validating batch mode."
        )
    lines.append(
        f"- This report used `{pool_workers}` pooled worker(s). Increase `--pool-workers` only after memory headroom is proven."
    )
    return lines


def run_recovery_check(
    fixture: str,
    *,
    timeout_s: float,
    max_rss_mb_hard: float,
) -> dict[str, Any]:
    """Force-kill one real worker via RSS limit, then verify the next task recovers."""
    path = FIX / fixture
    if not path.exists():
        return {
            "fixture": fixture,
            "forced_status": "error",
            "recovered_status": "error",
            "error": "fixture missing; run python tests/fixtures/fetch.py",
        }

    with DoclingWorkerPool(
        num_workers=1,
        timeout_s=timeout_s,
        max_rss_mb_hard=1,
        engine="docling",
        enable_ocr=False,
        enable_formula=False,
        poll_interval_s=0.05,
    ) as pool:
        forced = pool.convert(path)
        pool.max_rss_mb_hard = max_rss_mb_hard
        recovered = pool.convert(path)

    return {
        "fixture": fixture,
        "forced_status": forced.status,
        "forced_error": forced.error,
        "recovered_status": recovered.status,
        "recovered_engine": recovered.engine_used,
        "recovered_chars": len(recovered.markdown),
        "recovered_peak_rss_mb": recovered.peak_rss_mb or "—",
        "recovered_error": recovered.error,
    }


def _render_recovery_check(recovery: dict[str, Any]) -> list[str]:
    return [
        "",
        "## Recovery Check",
        "",
        "This opt-in check forces the first real worker to exceed a 1 MB RSS limit, then reruns the same PDF with the normal RSS limit.",
        "",
        "| Fixture | Forced status | Recovered status | Engine | Recovered chars | Recovered peak RSS (MB) | Error |",
        "|---|---|---|---|---|---|---|",
        (
            f"| `{recovery.get('fixture', '—')}` | {str(recovery.get('forced_status', 'unknown')).upper()} | "
            f"{str(recovery.get('recovered_status', 'unknown')).upper()} | "
            f"{recovery.get('recovered_engine', '—')} | {recovery.get('recovered_chars', '—')} | "
            f"{recovery.get('recovered_peak_rss_mb', '—')} | "
            f"`{_compact(str(recovery.get('recovered_error') or recovery.get('forced_error') or recovery.get('error') or ''))[:140]}` |"
        ),
    ]


def _row_from_result(result: WorkerPoolResult, fixture: str) -> dict[str, Any]:
    markdown = result.markdown or ""
    paperlm_dict = result.paperlm_dict or {}
    blocks = paperlm_dict.get("block_count")
    if not isinstance(blocks, int):
        raw_blocks = paperlm_dict.get("blocks")
        blocks = len(raw_blocks) if isinstance(raw_blocks, list) else 0

    return {
        "fixture": fixture,
        "status": result.status,
        "elapsed_s": round(result.elapsed_s, 2),
        "peak_rss_mb": result.peak_rss_mb if result.peak_rss_mb is not None else "—",
        "chars": len(markdown),
        "lines": len(markdown.splitlines()),
        "headings": _heading_count(markdown),
        "tables": _table_count(markdown),
        "blocks": blocks,
        "engine_used": result.engine_used,
        "first_line": _first_nonempty_line(markdown),
        "warnings": result.warnings,
        "error": result.error,
        "worker_index": result.worker_index,
    }


def _missing_row(fixture: str) -> dict[str, Any]:
    return {
        "fixture": fixture,
        "status": "error",
        "elapsed_s": 0,
        "peak_rss_mb": "—",
        "chars": 0,
        "lines": 0,
        "headings": 0,
        "tables": 0,
        "blocks": 0,
        "engine_used": "failed",
        "first_line": "",
        "warnings": [],
        "error": "fixture missing; run python tests/fixtures/fetch.py",
        "worker_index": "—",
    }


def _status_from_rows(rows: list[dict[str, Any]]) -> str:
    if rows and all(row.get("status") == "ok" for row in rows):
        return "ok"
    if any(row.get("status") == "ok" for row in rows):
        return "partial_error"
    guarded_status = next(
        (str(row["status"]) for row in rows if row.get("status") in {"timeout", "memory_limit"}),
        None,
    )
    if guarded_status:
        return guarded_status
    return "error"


def _max_peak(rows: list[dict[str, Any]]) -> float | str:
    peaks = [_to_float(row.get("peak_rss_mb")) for row in rows]
    numeric_peaks = [peak for peak in peaks if peak is not None]
    return round(max(numeric_peaks), 1) if numeric_peaks else "—"


def _first_nonempty_line(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return ""


def _heading_count(markdown: str) -> int:
    return sum(
        1
        for line in markdown.splitlines()
        if line.startswith("# ") or line.startswith("## ") or line.startswith("### ")
    )


def _table_count(markdown: str) -> int:
    return sum(1 for line in markdown.splitlines() if line.strip().startswith("|"))


def _compact(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--fixtures",
        default=",".join(DEFAULT_FIXTURES),
        help="Comma-separated fixture filenames.",
    )
    ap.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--max-rss-mb-hard", type=float, default=DEFAULT_MAX_RSS_MB_HARD)
    ap.add_argument(
        "--pool-workers",
        type=int,
        default=DEFAULT_POOL_WORKERS,
        help="Number of long-lived workers in pooled-worker mode.",
    )
    ap.add_argument(
        "--recovery-check",
        action="store_true",
        help="Force-kill one real worker via a 1 MB RSS limit, then verify restart recovery.",
    )
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if args.timeout_s <= 0:
        raise SystemExit("--timeout-s must be > 0")
    if args.max_rss_mb_hard <= 0:
        raise SystemExit("--max-rss-mb-hard must be > 0")
    if args.pool_workers <= 0:
        raise SystemExit("--pool-workers must be > 0")
    fixtures = [fixture.strip() for fixture in args.fixtures.split(",") if fixture.strip()]
    if not fixtures:
        raise SystemExit("--fixtures must not be empty")

    results = run_probe(
        fixtures,
        timeout_s=args.timeout_s,
        max_rss_mb_hard=args.max_rss_mb_hard,
        pool_workers=args.pool_workers,
    )
    recovery_check = (
        run_recovery_check(
            fixtures[0],
            timeout_s=args.timeout_s,
            max_rss_mb_hard=args.max_rss_mb_hard,
        )
        if args.recovery_check
        else None
    )
    REPORT.write_text(
        render_report(
            results,
            fixtures,
            timeout_s=args.timeout_s,
            max_rss_mb_hard=args.max_rss_mb_hard,
            pool_workers=args.pool_workers,
            recovery_check=recovery_check,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {REPORT}")


if __name__ == "__main__":
    main()
