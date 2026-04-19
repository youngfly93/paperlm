# Phase 5 — Competitor Comparison Framework

This file defines the comparison contract for `paperlm`.
It is intentionally narrower than an industry report: the goal is to
produce a **publishable benchmark baseline** that can support README,
GitHub release notes, issue threads, and launch posts.

## Benchmark Set

Use these tools as the default comparison set:

1. `MarkItDown baseline`
2. `paperlm`
3. `Docling standalone`
4. `Marker` (optional, if installed)
5. `MinerU` (optional, if installed)

The first three are the minimum set:

- `MarkItDown baseline` proves why `paperlm` should exist.
- `Docling standalone` proves `paperlm` is more than a thin wrapper.
- `paperlm` is the system under test.

## Dimensions

Split the comparison into two layers.

### 1. Static product dimensions

These come from official docs and do not require running code:

- license / commercial caveats
- output formats
- installation surface
- OCR / scanned-document positioning
- scope: generic docs vs scientific PDF specialization

### 2. Empirical conversion dimensions

These come from running the fixture corpus:

- conversion success rate
- latency
- peak RSS
- output size
- heading density
- table density
- formula markers
- obvious garbage leakage such as `(cid:)`

### 3. Human-review dimensions

These must be judged manually on selected outputs:

- text coverage of the main body
- reading-order correctness
- title / abstract placement
- table usability
- scanned OCR quality
- formula usefulness

## Scoring Rubric

Use a 0-3 rubric for human review.

- `0`: unusable
- `1`: partially usable, major cleanup needed
- `2`: usable with visible defects
- `3`: strong output, only minor defects

Recommended manual score columns:

- `text_coverage_score`
- `reading_order_score`
- `table_score`
- `ocr_score`
- `formula_score`

## Fixture Corpus

The current corpus is the existing `8`-PDF set already used elsewhere in
the repo:

- English double-column scientific paper
- Chinese double-column review
- English survey
- table-heavy paper
- math-heavy long paper
- long single-column survey
- 5-page scanned synthetic PDF
- 1-page scanned synthetic PDF

This is good enough for launch messaging, but not enough for a universal
"all scientific PDFs" claim.

## Claims You Can Safely Make

If the report stays green, you can usually support statements like:

- `paperlm` is stronger than baseline MarkItDown on scientific PDFs.
- `paperlm` offers a better Markdown/RAG landing zone than raw Docling in
  the tested corpus.
- scanned Chinese PDFs route correctly to PaddleOCR when OCR is installed.

## Claims You Should Avoid

Do not claim:

- universal PDF text coverage
- best-in-class performance across all scientific PDFs
- superiority over Marker or MinerU unless you have fresh empirical data
  from this exact corpus and environment

## Local Reproduction

Run:

```bash
python tests/fixtures/fetch.py
python benchmarks/phase5_competitor_compare.py
```

The generated report lands at:

```text
benchmarks/phase5_competitor_matrix.md
```
