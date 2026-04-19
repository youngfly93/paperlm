"""Phase 7 OCR confidence probe.

Runs the OCR engine on a small scanned fixture set and records page-level
confidence from ``IR.metadata["ocr"]``. Defaults to the 1-page scanned
fixture to keep memory and runtime bounded. Use ``--fixtures sample_scanned.pdf``
only when you explicitly want the slower 5-page run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parent
FIX = ROOT / "tests" / "fixtures"
REPORT = HERE / "phase7_ocr_confidence_report.md"

DEFAULT_FIXTURES = ("sample_scanned_1p.pdf",)
DEFAULT_TIMEOUT_S = 240.0
DEFAULT_MAX_RSS_MB_HARD = 4096.0

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.process_guard import run_guarded_subprocess  # noqa: E402

WORKER = r"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1])
SRC = ROOT / "src"
pdf_path = Path(sys.argv[2])

sys.path.insert(0, str(SRC))

t0 = time.perf_counter()
try:
    from markitdown import MarkItDown
    from markitdown_paperlm import register_converters

    md = MarkItDown()
    register_converters(md, paperlm_engine="ocr", paperlm_enable_ocr=True)
    result = md.convert(str(pdf_path))
    ir = result.ir
    ocr = ir.metadata.get("ocr", {})
    out = {
        "status": "ok" if result.markdown.strip() else "empty",
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "engine_used": result.engine_used,
        "blocks": len(ir.blocks),
        "warnings": ir.warnings,
        "ocr": ocr,
        "first_line": next((line.strip() for line in result.markdown.splitlines() if line.strip()), ""),
    }
except Exception as exc:
    out = {
        "status": "error",
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "engine_used": "failed",
        "blocks": 0,
        "warnings": [],
        "ocr": {},
        "first_line": "",
        "error": f"{type(exc).__name__}: {exc}",
    }

sys.stdout.write(json.dumps(out, ensure_ascii=True))
"""


def run_one(
    fixture: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
) -> dict[str, Any]:
    proc = run_guarded_subprocess(
        [sys.executable, "-c", WORKER, str(ROOT), str(FIX / fixture)],
        timeout_s=timeout_s,
        max_rss_mb_hard=max_rss_mb_hard,
    )
    if proc.status in {"timeout", "memory_limit"}:
        return {
            "fixture": fixture,
            "status": proc.status,
            "elapsed_s": proc.elapsed_s,
            "peak_mem_mb": proc.peak_rss_mb or "—",
            "engine_used": "failed",
            "blocks": 0,
            "warnings": [],
            "ocr": {},
            "first_line": "",
            "error": _guard_error(proc.error, proc.stderr),
        }
    if proc.returncode != 0 or not proc.stdout.strip():
        tail = " | ".join((proc.stderr or "").strip().splitlines()[-3:])
        return {
            "fixture": fixture,
            "status": "error",
            "elapsed_s": proc.elapsed_s,
            "peak_mem_mb": proc.peak_rss_mb or "—",
            "engine_used": "failed",
            "blocks": 0,
            "warnings": [],
            "ocr": {},
            "first_line": "",
            "error": tail or f"worker exit={proc.returncode}",
        }
    row = json.loads(proc.stdout)
    row["fixture"] = fixture
    if proc.peak_rss_mb is not None:
        row["peak_mem_mb"] = proc.peak_rss_mb
    return row


def render_report(
    rows: list[dict[str, Any]],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
) -> str:
    lines = [
        "# Phase 7 — OCR Confidence Probe",
        "",
        "_Focused scanned-PDF confidence report. Each fixture runs in a fresh subprocess._",
        "",
        f"Timeout: `{timeout_s:g}s`; RSS hard-kill threshold: `{max_rss_mb_hard:g} MB`.",
        "",
        "## Summary",
        "",
        "| Fixture | Status | Engine | Time (s) | Blocks | OCR mean | Min page | Low pages | Empty pages | Warnings | First line / error |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        ocr = row.get("ocr") or {}
        lines.append(
            f"| `{row['fixture']}` | {str(row['status']).upper()} | {row.get('engine_used', '—')} | "
            f"{row.get('elapsed_s', '—')} | {row.get('blocks', '—')} | "
            f"{_fmt_conf(ocr.get('mean_confidence'))} | {_fmt_conf(ocr.get('min_page_confidence'))} | "
            f"{_fmt_pages(ocr.get('low_confidence_pages'))} | {_fmt_pages(ocr.get('empty_pages'))} | "
            f"{len(row.get('warnings') or [])} | `{_esc(row.get('error') or row.get('first_line') or '')}` |"
        )

    lines.extend(["", "## Page Details", ""])
    for row in rows:
        lines.append(f"### `{row['fixture']}`")
        lines.append("")
        pages = (row.get("ocr") or {}).get("pages") or []
        if not pages:
            lines.append("_No OCR page metadata._")
            lines.append("")
            continue
        lines.append("| Page | Lines | Mean confidence | Min confidence |")
        lines.append("|---|---|---|---|")
        for page in pages:
            lines.append(
                f"| {page.get('page')} | {page.get('line_count')} | "
                f"{_fmt_conf(page.get('mean_confidence'))} | {_fmt_conf(page.get('min_confidence'))} |"
            )
        if row.get("warnings"):
            lines.append("")
            lines.append("Warnings:")
            for warning in row["warnings"]:
                lines.append(f"- {_esc(str(warning))}")
        lines.append("")
    return "\n".join(lines)


def _fmt_conf(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pages(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, list):
        return ",".join(str(page) for page in value)
    return str(value)


def _esc(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")[:160]


def _guard_error(error: str, stderr: str) -> str:
    tail = " | ".join((stderr or "").strip().splitlines()[-3:])
    if tail:
        return f"{error}: {tail[:200]}"
    return error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures",
        default=",".join(DEFAULT_FIXTURES),
        help="Comma-separated scanned fixture filenames.",
    )
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--max-rss-mb-hard", type=float, default=DEFAULT_MAX_RSS_MB_HARD)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.timeout_s <= 0:
        raise SystemExit("--timeout-s must be > 0")
    if args.max_rss_mb_hard <= 0:
        raise SystemExit("--max-rss-mb-hard must be > 0")
    fixtures = [fixture.strip() for fixture in args.fixtures.split(",") if fixture.strip()]
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        if not (FIX / fixture).exists():
            rows.append(
                {
                    "fixture": fixture,
                    "status": "error",
                    "elapsed_s": 0,
                    "engine_used": "failed",
                    "blocks": 0,
                    "warnings": ["fixture missing; run python tests/fixtures/fetch.py"],
                    "ocr": {},
                    "first_line": "",
                }
            )
            continue
        print(f">> OCR confidence :: {fixture}", flush=True)
        rows.append(
            run_one(
                fixture,
                timeout_s=args.timeout_s,
                max_rss_mb_hard=args.max_rss_mb_hard,
            )
        )

    REPORT.write_text(
        render_report(
            rows,
            timeout_s=args.timeout_s,
            max_rss_mb_hard=args.max_rss_mb_hard,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {REPORT}")


if __name__ == "__main__":
    main()
