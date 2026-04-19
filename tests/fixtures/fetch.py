"""Reproducibly build the test-fixture corpus.

Fixtures are NOT committed to git (see .gitignore). Run this script
once after cloning to download the 6 real PDFs and build the 2 synthetic
"scanned" PDFs (rasterized from the Chinese fixture).

Usage::

    python tests/fixtures/fetch.py           # full build
    python tests/fixtures/fetch.py --check   # list what's present, exit non-zero if any are missing

The corpus covers a spread of real-world cases — English double-column
learned articles, Chinese double-column journal articles, a math-heavy
LLM paper, a table-heavy benchmark paper, a long survey, and synthetic
scanned (image-only) PDFs for the OCR path.
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent


@dataclass(frozen=True)
class Fixture:
    filename: str
    url: str
    pages: int
    description: str


REAL_FIXTURES: list[Fixture] = [
    Fixture(
        "sample_en_two_col.pdf",
        "https://www.biorxiv.org/content/10.1101/2025.07.21.665920v1.full.pdf",
        pages=27,
        description="EN double-column bioRxiv bioinformatics benchmark paper",
    ),
    Fixture(
        "sample_zh_mixed.pdf",
        "https://lifescience.sinh.ac.cn/webadmin/upload/20241121140516_3869_1634.pdf",
        pages=10,
        description="ZH double-column 《生命科学》2024 bioinformatics review",
    ),
    Fixture(
        "sample_arxiv_llm_survey.pdf",
        "https://arxiv.org/pdf/2503.04490v3",
        pages=14,
        description="EN survey — LLMs in bioinformatics (moderate tables + figures)",
    ),
    Fixture(
        "sample_arxiv_table_heavy.pdf",
        "https://arxiv.org/pdf/2505.11545",
        pages=12,
        description="EN benchmark paper dense with tables (~5 tables in first 5 pages)",
    ),
    Fixture(
        "sample_arxiv_math.pdf",
        "https://arxiv.org/pdf/2501.12948",
        pages=86,
        description="EN long — DeepSeek-R1 technical report (math-heavy, 86 pages)",
    ),
    Fixture(
        "sample_arxiv_long_ir.pdf",
        "https://arxiv.org/pdf/2505.24758",
        pages=60,
        description="EN long survey — graph databases (long single-column flow)",
    ),
]

# Synthetic scanned fixtures (image-only PDFs rasterized from a real one).
SCANNED_SOURCE = "sample_zh_mixed.pdf"
SYNTHETIC_FIXTURES = [
    # (output, max_pages, dpi)
    ("sample_scanned.pdf", 5, 150),
    ("sample_scanned_1p.pdf", 1, 150),
]


def fetch_one(fx: Fixture, force: bool = False) -> None:
    out = HERE / fx.filename
    if out.exists() and not force:
        print(f"  exists — {fx.filename}")
        return
    print(f"  fetching {fx.url} -> {fx.filename}")
    urllib.request.urlretrieve(fx.url, out)
    size = out.stat().st_size
    if size < 10_000:
        raise RuntimeError(
            f"{fx.filename} is suspiciously small ({size} bytes); "
            "the source may require authentication or have moved. "
            f"URL: {fx.url}"
        )


def build_scanned_fixtures(force: bool = False) -> None:
    import pypdfium2 as pdfium
    from PIL import Image

    src = HERE / SCANNED_SOURCE
    if not src.exists():
        raise RuntimeError(f"cannot build scanned fixtures: {SCANNED_SOURCE} missing")

    for out_name, max_pages, dpi in SYNTHETIC_FIXTURES:
        out = HERE / out_name
        if out.exists() and not force:
            print(f"  exists — {out_name}")
            continue
        print(f"  rasterizing {SCANNED_SOURCE}[:{max_pages}] @ {dpi}dpi -> {out_name}")

        pdf = pdfium.PdfDocument(str(src))
        scale = dpi / 72.0
        n = min(len(pdf), max_pages)
        images: list[Image.Image] = []
        for i in range(n):
            page = pdf[i]
            images.append(page.render(scale=scale).to_pil().convert("RGB"))
            page.close()
        pdf.close()

        images[0].save(
            out,
            save_all=True,
            append_images=images[1:],
            format="PDF",
            resolution=dpi,
        )


def all_expected_names() -> list[str]:
    names = [fx.filename for fx in REAL_FIXTURES]
    names += [t[0] for t in SYNTHETIC_FIXTURES]
    return names


def check_present() -> int:
    missing = [n for n in all_expected_names() if not (HERE / n).exists()]
    if missing:
        print("MISSING fixtures (run `python tests/fixtures/fetch.py`):")
        for n in missing:
            print(f"  - {n}")
        return 1
    print(f"All {len(all_expected_names())} fixtures present.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="list missing fixtures; exit 1 if any")
    ap.add_argument("--force", action="store_true", help="re-download even if file exists")
    args = ap.parse_args()

    if args.check:
        sys.exit(check_present())

    print(f"Fixture corpus ({len(REAL_FIXTURES)} real + {len(SYNTHETIC_FIXTURES)} synthetic):\n")
    print("Real PDFs")
    print("---------")
    for fx in REAL_FIXTURES:
        print(f"  {fx.filename:40s} {fx.description}")
        fetch_one(fx, force=args.force)

    print("\nSynthetic (scanned) PDFs")
    print("------------------------")
    build_scanned_fixtures(force=args.force)

    print("\nDone.")
    sys.exit(check_present())


if __name__ == "__main__":
    main()
