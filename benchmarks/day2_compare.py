"""Week 1 Day 2 benchmark: MarkItDown baseline vs Docling standalone.

Runs 3 fixtures × 2 engines, records per-run:
  - wall time
  - output length
  - first 300 char snippet
Writes a Markdown summary to benchmarks/day2_baseline.md and saves full
outputs to benchmarks/outputs/{fixture}__{engine}.md
"""

from __future__ import annotations

import time
from pathlib import Path

from docling.document_converter import DocumentConverter as DoclingConverter
from markitdown import MarkItDown

HERE = Path(__file__).parent
FIX = HERE.parent / "tests" / "fixtures"
OUT = HERE / "outputs"
OUT.mkdir(exist_ok=True)

FIXTURES = [
    ("sample_en_two_col.pdf", "EN double-column, bioRxiv 2025 RNA-seq benchmark (27 pages)"),
    ("sample_zh_mixed.pdf", "ZH mixed, 《生命科学》2024 bioinformatics review (10 pages)"),
    ("sample_scanned.pdf", "Scanned, rasterized ZH paper, 5 pages, NO text layer"),
]


def run_markitdown(pdf_path: Path) -> tuple[str, float]:
    md = MarkItDown()  # no plugins — pure baseline
    t0 = time.perf_counter()
    result = md.convert(str(pdf_path))
    return result.markdown, time.perf_counter() - t0


def run_docling(pdf_path: Path) -> tuple[str, float]:
    dc = DoclingConverter()
    t0 = time.perf_counter()
    result = dc.convert(str(pdf_path))
    md = result.document.export_to_markdown()
    return md, time.perf_counter() - t0


def main() -> None:
    lines: list[str] = [
        "# Day 2 Baseline: MarkItDown vs Docling",
        "",
        "_Week 1 Day 2 — Eyeball comparison on 3 representative fixtures._",
        "",
        "All runs CPU-only. Times include engine init + conversion.",
        "",
    ]

    for fname, desc in FIXTURES:
        pdf = FIX / fname
        if not pdf.exists():
            lines.append(f"## {fname}\n\n**MISSING**\n")
            continue

        lines.append(f"## {fname}\n\n**{desc}**\n")

        results: list[tuple[str, str, float, int]] = []

        # MarkItDown baseline
        try:
            md_txt, md_t = run_markitdown(pdf)
            (OUT / f"{pdf.stem}__markitdown.md").write_text(md_txt)
            results.append(("MarkItDown (baseline)", md_txt, md_t, len(md_txt)))
        except Exception as e:
            results.append(("MarkItDown (baseline)", f"ERROR: {e}", 0.0, 0))

        # Docling
        try:
            doc_txt, doc_t = run_docling(pdf)
            (OUT / f"{pdf.stem}__docling.md").write_text(doc_txt)
            results.append(("Docling 2.90", doc_txt, doc_t, len(doc_txt)))
        except Exception as e:
            results.append(("Docling 2.90", f"ERROR: {e}", 0.0, 0))

        lines.append("| Engine | Time (s) | Output chars | First 200 chars |")
        lines.append("|---|---|---|---|")
        for engine, text, t, length in results:
            snippet = text[:200].replace("\n", " ").replace("|", "\\|")
            lines.append(f"| {engine} | {t:.1f} | {length} | `{snippet}...` |")
        lines.append("")

        # Full snippet
        for engine, text, _, _ in results:
            lines.append(f"<details><summary>{engine} — first 800 chars</summary>\n\n```\n{text[:800]}\n```\n\n</details>\n")
        lines.append("---\n")

    report = HERE / "day2_baseline.md"
    report.write_text("\n".join(lines))
    print(f"Wrote {report}")
    print(f"Full outputs saved to {OUT}/")


if __name__ == "__main__":
    main()
