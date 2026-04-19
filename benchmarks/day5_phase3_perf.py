"""Week 3 Day 5 — Phase 3 performance benchmark.

Measures wall time + peak memory for Docling-backed conversion of our
three canonical fixtures. Writes results to ``phase3_perf.md`` beside
this file. Intentionally runs engines *sequentially in separate Python
processes* to keep peak memory accurate (Docling + PaddleOCR loaded
together would compound RSS by ~2-3 GB).
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
FIX = HERE.parent / "tests" / "fixtures"
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)
REPORT = HERE / "phase3_perf.md"

PLAN = [
    ("sample_en_two_col.pdf", "EN 27p double-column bioRxiv paper", "docling"),
    ("sample_zh_mixed.pdf", "ZH 10p mixed bioinformatics review", "docling"),
    ("sample_scanned_1p.pdf", "Scanned ZH, 1p, no text layer", "ocr"),
]

WORKER_SCRIPT = r"""
import io, os, sys, time, json, resource

pdf_path = sys.argv[1]
engine   = sys.argv[2]
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

with open(pdf_path, "rb") as f:
    data = f.read()

from markitdown_paperlm.router import EngineRouter
t0 = time.perf_counter()
router = EngineRouter(engine=engine)
ir = router.convert(io.BytesIO(data))
elapsed = time.perf_counter() - t0

# ru_maxrss on macOS is bytes, on Linux KB. Normalize to MB.
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform == "darwin":
    peak_mb = rss / (1024 * 1024)
else:
    peak_mb = rss / 1024

out = {
    "engine_used": ir.engine_used,
    "n_blocks":    len(ir.blocks),
    "warnings":    ir.warnings[:5],
    "elapsed_s":   round(elapsed, 2),
    "peak_mem_mb": round(peak_mb, 1),
}
sys.stdout.write(json.dumps(out))
"""


def run_one(pdf: Path, engine: str) -> dict:
    """Run conversion in a fresh subprocess so peak memory is isolated."""
    proc = subprocess.run(
        [sys.executable, "-c", WORKER_SCRIPT, str(pdf), engine],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return {
            "engine_used": "error",
            "error": proc.stderr.strip().splitlines()[-1] if proc.stderr else "no output",
        }
    # Worker prints a single JSON line on stdout; training noise may precede.
    last_line = proc.stdout.strip().splitlines()[-1]
    return json.loads(last_line)


def main() -> None:
    lines: list[str] = [
        "# Phase 3 Performance Benchmark",
        "",
        "_Week 3 Day 5 — each fixture converted in an isolated subprocess._",
        "",
        f"Platform: {sys.platform} · Python {sys.version.split()[0]} · CPU-only",
        "",
        "| Fixture | Engine | Time (s) | Peak RSS (MB) | IR Blocks | Warnings |",
        "|---|---|---|---|---|---|",
    ]

    results: list[tuple[str, dict]] = []
    for fname, desc, engine in PLAN:
        path = FIX / fname
        if not path.exists():
            results.append((fname, {"engine_used": "missing", "error": "fixture absent"}))
            continue
        print(f"Running {fname} with engine={engine} ...", flush=True)
        t0 = time.time()
        res = run_one(path, engine)
        print(f"  -> {res} (wall {time.time()-t0:.1f}s)", flush=True)
        results.append((fname, res))

    for fname, res in results:
        line = (
            f"| `{fname}` | {res.get('engine_used', '?')} "
            f"| {res.get('elapsed_s', '—')} "
            f"| {res.get('peak_mem_mb', '—')} "
            f"| {res.get('n_blocks', '—')} "
            f"| {len(res.get('warnings', []) or [])} |"
        )
        lines.append(line)

    # Descriptions + full-output dump
    lines.append("")
    lines.append("## Fixture descriptions")
    lines.append("")
    for fname, desc, engine in PLAN:
        lines.append(f"- **`{fname}`** — {desc} (engine: `{engine}`)")
    lines.append("")

    lines.append("## Targets from PRD §5.1 (v0.1)")
    lines.append("")
    lines.append("| Metric | Target | Observed |")
    lines.append("|---|---|---|")

    en_res = next(
        (r for name, r in results if name == "sample_en_two_col.pdf"), {}
    )
    zh_res = next(
        (r for name, r in results if name == "sample_zh_mixed.pdf"), {}
    )
    scan_res = next(
        (r for name, r in results if name == "sample_scanned_1p.pdf"), {}
    )

    def fmt(res: dict, key: str, unit: str = "") -> str:
        v = res.get(key)
        return f"{v}{unit}" if v is not None else "—"

    lines.append(
        f"| 20p English paper ≤ 90s (Docling, CPU) | **≤ 90 s** | "
        f"{fmt(en_res, 'elapsed_s', ' s')} (27 pages → scaled = "
        f"{round(en_res.get('elapsed_s', 0) * 20 / 27, 1) if en_res.get('elapsed_s') else '—'} s/20p) |"
    )
    lines.append(
        f"| Chinese 10p non-scanned | — | {fmt(zh_res, 'elapsed_s', ' s')} |"
    )
    lines.append(
        f"| Scanned 1p via PaddleOCR | — | {fmt(scan_res, 'elapsed_s', ' s')} |"
    )
    lines.append(
        f"| Peak memory ≤ 4 GB (excl. models) | **≤ 4 GB** | "
        f"EN: {fmt(en_res, 'peak_mem_mb', ' MB')} · "
        f"ZH: {fmt(zh_res, 'peak_mem_mb', ' MB')} · "
        f"scan: {fmt(scan_res, 'peak_mem_mb', ' MB')} |"
    )
    lines.append("")

    REPORT.write_text("\n".join(lines))
    print(f"\nWrote {REPORT}")


if __name__ == "__main__":
    main()
