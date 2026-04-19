"""Week 4 Day 5 — integration sweep across the full fixture corpus.

Runs each of the 8 fixtures through the production EngineRouter
(choosing ``docling`` for text PDFs and ``ocr`` for scanned ones), in
isolated subprocesses so peak RSS is per-fixture rather than cumulative.

Writes ``benchmarks/phase4_integration.md`` with a full observation
matrix. Fixtures larger than ``BIG_PAGE_CUTOFF`` pages are flagged as
"long-form" — we still run them but with a Docling document timeout so
the sweep cannot hang the machine.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
FIX = HERE.parent / "tests" / "fixtures"
REPORT = HERE / "phase4_integration.md"

BIG_PAGE_CUTOFF = 30  # fixtures above this get a timeout + "long-form" tag

# (filename, suggested_engine, page_count, description)
PLAN: list[tuple[str, str, int, str]] = [
    ("sample_en_two_col.pdf", "docling", 27, "EN double-column bioRxiv"),
    ("sample_zh_mixed.pdf", "docling", 10, "ZH double-column review"),
    ("sample_arxiv_llm_survey.pdf", "docling", 14, "EN survey"),
    ("sample_arxiv_table_heavy.pdf", "docling", 12, "EN table-heavy"),
    ("sample_arxiv_math.pdf", "docling", 86, "EN long math-heavy (DeepSeek-R1)"),
    ("sample_arxiv_long_ir.pdf", "docling", 60, "EN long single-column survey"),
    ("sample_scanned.pdf", "ocr", 5, "synthetic 5p scanned"),
    ("sample_scanned_1p.pdf", "ocr", 1, "synthetic 1p scanned"),
]


WORKER = r"""
import io, os, sys, time, json, resource

pdf_path    = sys.argv[1]
engine      = sys.argv[2]
timeout_s   = float(sys.argv[3])  # 0 = no timeout

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

with open(pdf_path, "rb") as f:
    data = f.read()

from markitdown_paperlm.router import EngineRouter

# For long documents we patch Docling's pipeline to include a document-level
# timeout. The adapter-level convert() will honor it and return partial IR.
if timeout_s > 0 and engine == "docling":
    try:
        from markitdown_paperlm.engines.docling_adapter import DoclingAdapter
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        po = PdfPipelineOptions()
        po.document_timeout = timeout_s
        DoclingAdapter._converters[False] = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=po)}
        )
    except Exception as exc:
        print(f"warn: could not set Docling timeout: {exc}", file=sys.stderr)

t0 = time.perf_counter()
router = EngineRouter(engine=engine)
ir = router.convert(io.BytesIO(data))
elapsed = time.perf_counter() - t0

rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
peak_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024

# First non-empty block content as a smoke indicator.
first_content = ""
for b in ir.blocks:
    if b.content and b.content.strip():
        first_content = b.content.strip().replace("\n", " ")[:100]
        break

sys.stdout.write(json.dumps({
    "engine_used":  ir.engine_used,
    "n_blocks":     len(ir.blocks),
    "n_warnings":   len(ir.warnings),
    "warnings":     ir.warnings[:2],
    "first_block":  first_content,
    "elapsed_s":    round(elapsed, 2),
    "peak_mem_mb":  round(peak_mb, 1),
}))
"""


def run_one(fname: str, engine: str, timeout_s: float = 0) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", WORKER, str(FIX / fname), engine, str(timeout_s)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        return {"error": " | ".join(tail)[:200]}
    for line in reversed(proc.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {"error": "no JSON payload"}


def main() -> None:
    print(f"Integration sweep — {len(PLAN)} fixtures, isolated subprocesses")
    print(f"Platform: {sys.platform} · Python {sys.version.split()[0]}\n")

    results: list[tuple[tuple, dict]] = []
    for fname, engine, pages, desc in PLAN:
        if not (FIX / fname).exists():
            print(f"[SKIP] {fname} missing — run python tests/fixtures/fetch.py")
            continue
        timeout_s = 90.0 if pages > BIG_PAGE_CUTOFF else 0.0
        label = f"{fname} ({pages}p, engine={engine}"
        if timeout_s > 0:
            label += f", timeout={int(timeout_s)}s"
        label += ")"
        print(f">> {label}", flush=True)
        res = run_one(fname, engine, timeout_s)
        print(f"   -> {res}\n", flush=True)
        results.append(((fname, engine, pages, desc), res))

    _write_report(results)


def _write_report(results: list[tuple[tuple, dict]]) -> None:
    lines: list[str] = [
        "# Phase 4 — Integration Sweep",
        "",
        "_Week 4 Day 5 — every fixture end-to-end through the production router._",
        "",
        f"Platform: {sys.platform} · Python {sys.version.split()[0]} · CPU-only",
        "",
        "Each row is an isolated subprocess (fresh Docling / PaddleOCR state).",
        f"Fixtures > {BIG_PAGE_CUTOFF} pages are run with a 90-second Docling",
        "document timeout; a timeout is treated as expected, not a failure.",
        "",
        "| Fixture | Pages | Engine | Time (s) | Peak RSS (MB) | Blocks | Warnings |",
        "|---|---|---|---|---|---|---|",
    ]
    for (fname, engine, pages, desc), res in results:
        if "error" in res:
            lines.append(
                f"| `{fname}` | {pages} | {engine} | — | — | — | ERROR: {res['error']} |"
            )
            continue
        rss = res.get("peak_mem_mb", 0)
        rss_tag = "✅" if rss <= 4096 else "⚠️"
        lines.append(
            f"| `{fname}` | {pages} | {res.get('engine_used')} "
            f"| {res.get('elapsed_s')} | {rss_tag} {rss} "
            f"| {res.get('n_blocks')} | {res.get('n_warnings')} |"
        )

    lines.append("")
    lines.append("## Fixture descriptions")
    lines.append("")
    for (fname, engine, pages, desc), _ in results:
        lines.append(f"- **`{fname}`** ({pages}p, engine `{engine}`) — {desc}")
    lines.append("")

    lines.append("## First-block smoke evidence")
    lines.append("")
    lines.append("The first non-empty block from each fixture's IR, truncated.")
    lines.append("This is the cheapest indicator that the conversion actually ran.")
    lines.append("")
    for (fname, _, _, _), res in results:
        if "error" in res:
            lines.append(f"- `{fname}`: ❌ {res['error']}")
        else:
            lines.append(
                f"- `{fname}`: `{res.get('first_block', '')[:90]}...`"
            )
    lines.append("")

    # PRD gates
    en = next((r for (f, *_), r in results if f == "sample_en_two_col.pdf"), {})
    scan = next((r for (f, *_), r in results if f == "sample_scanned_1p.pdf"), {})

    lines.append("## PRD §5.1 gate checklist (v0.1)")
    lines.append("")
    lines.append("| Metric | Target | Observed |")
    lines.append("|---|---|---|")
    if en and "elapsed_s" in en:
        scaled = round(en["elapsed_s"] * 20 / 27, 1)
        lines.append(
            f"| 20p English paper ≤ 90s (Docling, CPU) | **≤ 90 s** | "
            f"27p run = {en['elapsed_s']} s → scaled to 20p = {scaled} s |"
        )
    over_budget = [
        (f, r.get("peak_mem_mb", 0))
        for (f, *_), r in results
        if r.get("peak_mem_mb", 0) > 4096
    ]
    if over_budget:
        lines.append(
            "| Peak memory ≤ 4 GB per fixture | **≤ 4 GB** | "
            f"❌ over budget: {over_budget} |"
        )
    else:
        lines.append(
            "| Peak memory ≤ 4 GB per fixture | **≤ 4 GB** | "
            f"✅ every fixture under budget |"
        )
    if scan and "engine_used" in scan:
        lines.append(
            f"| Scanned PDF yields recognizable text | — | "
            f"engine={scan['engine_used']}, blocks={scan.get('n_blocks')} "
            f"(first: {scan.get('first_block', '')[:60]!r}) |"
        )
    lines.append("")

    REPORT.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {REPORT}")


if __name__ == "__main__":
    main()
