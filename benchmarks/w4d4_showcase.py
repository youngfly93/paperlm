"""Week 4 Day 4 — generate README before/after evidence.

Runs each real fixture through:
  1. MarkItDown baseline (no plugin)
  2. paperlm (enable_plugins=True, full Week 3 pipeline)

Saves both outputs to benchmarks/outputs/ and prints a side-by-side diff
for the first ~600 chars of each so we can pick the most compelling
snippets for the README.

Run in its own process because Docling + MarkItDown built-in PDF
converter share pdfminer state and we want clean measurements.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
FIX = HERE.parent / "tests" / "fixtures"
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)

TARGETS = [
    "sample_en_two_col.pdf",
    "sample_zh_mixed.pdf",
    "sample_arxiv_table_heavy.pdf",
]

WORKER = r"""
import io, sys, json, time
from markitdown import MarkItDown

pdf_path  = sys.argv[1]
use_plugin = sys.argv[2] == "plugin"

md = MarkItDown(enable_plugins=use_plugin)
t0 = time.perf_counter()
result = md.convert(pdf_path)
elapsed = time.perf_counter() - t0

engine = getattr(result, "engine_used", "builtin")
sys.stdout.write(json.dumps({
    "markdown": result.markdown,
    "engine_used": engine,
    "elapsed_s": round(elapsed, 2),
}))
"""


def run(pdf: Path, use_plugin: bool) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", WORKER, str(pdf), "plugin" if use_plugin else "builtin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return {"error": (proc.stderr or "no output")[:400]}
    # Last line of stdout is our JSON; preceding noise is tokenizer/model logs.
    for line in reversed(proc.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return {"error": "no JSON payload"}


def main() -> None:
    for fname in TARGETS:
        pdf = FIX / fname
        if not pdf.exists():
            print(f"[SKIP] {fname} missing — run python tests/fixtures/fetch.py")
            continue

        print(f"\n================  {fname}  ================")
        for tag, use_plugin in [("baseline", False), ("paperlm", True)]:
            res = run(pdf, use_plugin)
            if "error" in res:
                print(f"  [{tag}] ERROR: {res['error'][:200]}")
                continue
            path = OUT / f"{pdf.stem}__{tag}.md"
            path.write_text(res["markdown"] or "")
            head = (res["markdown"] or "").split("\n", 20)[:12]
            print(
                f"  [{tag}] engine={res.get('engine_used')!s:18s} "
                f"time={res['elapsed_s']}s  chars={len(res['markdown'])}  -> {path.name}"
            )
            print("  ---- first 12 lines ----")
            for ln in head:
                print(f"    {ln[:110]}")
            print()


if __name__ == "__main__":
    main()
