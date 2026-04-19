# Polish Plan

This plan turns the current alpha into a more trustworthy scientific
PDF-to-RAG entry point. The priority is output quality and evidence, not
feature sprawl.

## Step 1 — Front-Matter Quality

Goal: generated Markdown should start with the paper title when a plausible
title exists.

Status: implemented.

Acceptance:

- First-page affiliation / email / DOI furniture does not appear before the title.
- Author-list fragments are not promoted as titles.
- The benchmark report tracks title-like first-line count.

## Step 2 — Structured Sidecars

Goal: `paperlm` should not be just a Markdown wrapper around Docling.

Status: implemented.

Acceptance:

- `result.paperlm_dict` exposes a JSON-serializable IR.
- `result.paperlm_json` exposes the same IR as JSON text.
- `result.paperlm_chunks_jsonl` exposes one text-bearing block per JSONL line.

## Step 3 — Text Recall And Reading-Order Evidence

Goal: measure whether the main body is present and readable, not just whether
conversion succeeded.

Status: implemented.

Acceptance:

- Add a benchmark that compares text recall against a reference extraction or
  manually curated snippets.
- Track title / abstract / introduction ordering separately.
- Keep the metric corpus small enough to run before every release.

## Step 4 — OCR Confidence

Goal: make scanned output auditable.

Status: implemented.

Acceptance:

- Store page-level OCR confidence in IR metadata.
- Flag low-confidence pages in `ir.warnings`.
- Include OCR confidence in benchmark reports.

## Step 5 — Performance Guardrails

Goal: stop long and math-heavy documents from dominating runtime.

Status: implemented.

Acceptance:

- Keep the default competitor benchmark on a smoke profile, not the full
  corpus.
- Add per-tool/per-fixture subprocess timeouts so a single parser cannot hang
  the run.
- Add hard RSS limits that kill only the worker process tree when a parser
  exceeds the configured memory budget.
- Add benchmark warnings for timeouts, high RSS, and any `paperlm` fixture that
  is more than 3x slower than Docling.
- Keep formula LaTeX enrichment opt-in by default and provide a long-PDF probe
  for timing `scanned_check`, Docling conversion, IR post-processing,
  Markdown rendering, and sidecar serialization separately.
- Add an opt-in cProfile mode for the long-PDF probe so post-processing
  algorithmic regressions can be diagnosed before adding chunked mode.
- Add a worker-pool probe to quantify cold-start amortization for batch
  ingestion before changing the production conversion API.
- Add a service-side `DoclingWorkerPool` API that reuses worker subprocesses,
  applies per-task timeout/RSS limits, and auto-restarts failed workers.
- Add a `paperlm-batch` CLI for JSONL/file-list batch ingestion that uses the
  guarded worker pool and writes Markdown/IR/chunk artifacts.

## Step 6 — Broader Competitor Evidence

Goal: compare against heavy parsers only when the local evidence is real.

Acceptance:

- Install and run Marker / MinerU on the same 8-PDF corpus.
- Do not claim superiority unless the generated report contains fresh empirical
  data for that tool.
