"""Week 4 Day 1 probe — find a PaddleOCR config with RSS <= 4 GB.

Runs several config variants against the 1-page scanned fixture in
isolated subprocesses and reports wall time + peak RSS + recognition
quality (n text lines). Writes phase4_rss_probe.md next to this script.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
FIX = HERE.parent / "tests" / "fixtures" / "sample_scanned_1p.pdf"
REPORT = HERE / "phase4_rss_probe.md"


# Each variant is a dict passed through to the worker as JSON.
VARIANTS: list[dict] = [
    {
        "label": "A: baseline (server models, 150 dpi)",
        "models": "server",
        "dpi": 150,
        "gc_per_page": False,
        "paddle_env": {},
    },
    {
        "label": "B: server + gc + paddle flags",
        "models": "server",
        "dpi": 150,
        "gc_per_page": True,
        "paddle_env": {
            "FLAGS_allocator_strategy": "naive_best_fit",
            "FLAGS_fraction_of_cpu_memory_to_use": "0",
        },
    },
    {
        "label": "C: mobile models (150 dpi)",
        "models": "mobile",
        "dpi": 150,
        "gc_per_page": False,
        "paddle_env": {},
    },
    {
        "label": "D: mobile models (120 dpi)",
        "models": "mobile",
        "dpi": 120,
        "gc_per_page": False,
        "paddle_env": {},
    },
    {
        "label": "E: mobile + 120 dpi + gc + paddle flags",
        "models": "mobile",
        "dpi": 120,
        "gc_per_page": True,
        "paddle_env": {
            "FLAGS_allocator_strategy": "naive_best_fit",
            "FLAGS_fraction_of_cpu_memory_to_use": "0",
        },
    },
]


WORKER_SCRIPT = r"""
import os, sys, io, gc, time, json, resource

cfg = json.loads(sys.argv[1])
pdf_path = sys.argv[2]

# Set paddle flags BEFORE importing paddleocr.
for k, v in (cfg.get("paddle_env") or {}).items():
    os.environ[k] = str(v)
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

import numpy as np
import pypdfium2 as pdfium
from paddleocr import PaddleOCR

models = cfg["models"]
dpi = int(cfg["dpi"])
gc_per_page = bool(cfg.get("gc_per_page", False))

kwargs = dict(
    use_textline_orientation=False,
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
)
if models == "mobile":
    kwargs.update(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
    )
else:
    kwargs["lang"] = "ch"  # use server defaults via lang

t0 = time.perf_counter()
ocr = PaddleOCR(**kwargs)

# Render + OCR the single fixture page.
with open(pdf_path, "rb") as f:
    data = f.read()
pdf = pdfium.PdfDocument(data)
pil = pdf[0].render(scale=dpi/72.0).to_pil().convert("RGB")
pdf.close()
arr = np.array(pil)
del pil
if gc_per_page:
    gc.collect()

out = ocr.predict(arr)
del arr
if gc_per_page:
    gc.collect()

elapsed = time.perf_counter() - t0
n_texts = len(out[0].get("rec_texts", [])) if out else 0

rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
peak_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024

sys.stdout.write(json.dumps({
    "elapsed_s": round(elapsed, 2),
    "peak_mem_mb": round(peak_mb, 1),
    "n_text_lines": n_texts,
}))
"""


def run_variant(cfg: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", WORKER_SCRIPT, json.dumps(cfg), str(FIX)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        err_tail = (proc.stderr or "").strip().splitlines()[-3:]
        return {"error": " | ".join(err_tail) or "no output"}
    last = proc.stdout.strip().splitlines()[-1]
    try:
        return json.loads(last)
    except json.JSONDecodeError:
        return {"error": f"bad json: {last!r}"}


def main() -> None:
    if not FIX.exists():
        print(f"fixture missing: {FIX}", file=sys.stderr)
        sys.exit(1)

    print("Running RSS probe — each variant in an isolated subprocess")
    print("=" * 70)

    results: list[tuple[dict, dict]] = []
    for cfg in VARIANTS:
        print(f"\n{cfg['label']}")
        res = run_variant(cfg)
        print(f"  {res}")
        results.append((cfg, res))

    lines: list[str] = [
        "# Phase 4 — RSS Probe for PaddleOCR",
        "",
        "_Week 4 Day 1 — one-page scanned fixture, isolated subprocesses._",
        "",
        "Goal: find a PaddleOCR configuration with peak RSS ≤ 4 GB (PRD §5.1).",
        "",
        "| Variant | Wall (s) | Peak RSS (MB) | Text lines | Notes |",
        "|---|---|---|---|---|",
    ]
    for cfg, res in results:
        if "error" in res:
            lines.append(f"| {cfg['label']} | — | — | — | ERROR: {res['error']} |")
        else:
            tag = "✅" if res["peak_mem_mb"] <= 4096 else "❌"
            lines.append(
                f"| {cfg['label']} | {res['elapsed_s']} "
                f"| {tag} {res['peak_mem_mb']} "
                f"| {res['n_text_lines']} | |"
            )

    REPORT.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {REPORT}")


if __name__ == "__main__":
    main()
