# paperlm

[![CI](https://github.com/youngfly93/paperlm/actions/workflows/test.yml/badge.svg)](https://github.com/youngfly93/paperlm/actions/workflows/test.yml)

> **Scientific PDFs → Markdown, built for LLMs.**
> A MarkItDown plugin that replaces the built-in PDF converter with Docling-powered layout analysis and PaddleOCR for scanned documents.

**Status**: ✅ v0.1.1 released on PyPI. `main` is preparing v0.1.2
with lazy sidecar generation and CI hardening.

中文版说明见 [README_zh.md](README_zh.md)。

## Why

MarkItDown's built-in PDF path is optimized for invoices and form-style
documents; its own source code acknowledges it is *"not [designed] for
multi-column text layouts in scientific documents"*. This plugin fixes
that for research use-cases.

### Before / After, case 1 — arXiv table-heavy paper

On [arXiv:2505.11545](https://arxiv.org/abs/2505.11545) (the TARGET
benchmark paper), MarkItDown's built-in heuristics mistake the title
block for a GitHub-flavored table and produce this garbage:

```markdown
|     | TARGET: |     | Benchmarking |     |     | Table | Retrieval | for Generative |     | Tasks |
| --- | ------- | --- | ------------ | --- | --- | ----- | --------- | -------------- | --- | ----- |
XingyuJi*1,ParkerGlenn2,AdityaG.Parameswaran1,MadelonHulsebos3
|     |     |     |          | 1UCBerkeley |     |     | 2CapitalOne          | 3CWI |         |
| --- | --- | --- | -------- | ----------- | --- | --- | -------------------- | ---- | ------- |
5202 yaM 41  ]RI.sc[  1v54511.5052:viXra Thedatalandscapeisrichwithstructureddata,
```

With `paperlm` enabled, the same page renders as:

```markdown
## TARGET: Benchmarking Table Retrieval for Generative Tasks

> * Correspondence to madelon.hulsebos@cwi.nl and jixy2012@berkeley.edu

Large Language Models (LLMs) have become an indispensable tool in the
knowledge worker's arsenal, providing a treasure trove of information at
one's fingertips. Retrieval-Augmented Generation (RAG) (Lewis et al., 2020)
further extends the capabilities of these LLMs by grounding generic dialog...

## 1 Introduction

The data landscape is rich with structured data, often of high value to
organizations, driving important applications in data analysis and
machine learning. Recent progress in representation learning and
generative models for such data has led to the development of natural
language interfaces to structured data, including those leveraging
text-to-SQL...
```

The garbage tables are gone, the vertical arXiv watermark
(`5202 yaM 41 ]RI.sc[` = `51 May 2025 [cs.IR]` read bottom-up) is
stripped, paragraphs reflow, and the title picks up a proper `##`
heading.

### Before / After, case 2 — 27-page bioRxiv benchmark

| | MarkItDown baseline | paperlm |
|---|---|---|
| First output | `bioRxiv preprint doi:...` watermark | `## A systematic benchmark...` (H2) |
| Authors | `AliHamraoui1,2,AudreyOnfroy3,...` glued | `Ali Hamraoui 1,2 , Audrey Onfroy 3 , ...` |
| Special chars | `(cid:0)` garbage | `/a0` readable |
| Paragraph structure | hard-wrapped soup | clean paragraphs |

Reproduce both side-by-sides with:

```bash
python tests/fixtures/fetch.py          # build the corpus
python benchmarks/w4d4_showcase.py      # write outputs to benchmarks/outputs/
diff benchmarks/outputs/sample_arxiv_table_heavy__{baseline,paperlm}.md
```

### Known limit — bilingual documents

Papers that put a Chinese title/abstract *right next to* the English
title/abstract on the same page (as the 《生命科学》 fixture does)
still surface with interleaved ordering; Docling's layout model
sometimes reorders these blocks. We will revisit in a later pass.

## Install

```bash
# From PyPI
pip install paperlm[docling]            # default — Docling engine
pip install paperlm[docling,ocr]        # + PaddleOCR for scanned
pip install paperlm[all]                # all safe-license extras

# From source (contributor flow)
git clone https://github.com/youngfly93/paperlm
cd paperlm
pip install -e ".[docling,dev]"
```

## Usage

```python
from markitdown import MarkItDown

md = MarkItDown(enable_plugins=True)
result = md.convert("paper.pdf")

# Stable MarkItDown API
print(result.markdown)

# paperlm extensions (non-stable API — Python only, not exposed to CLI/MCP)
print(result.engine_used)       # "docling" / "paddleocr" / "pdfminer" / "failed"
print(len(result.ir.blocks))    # structured IR for downstream RAG/Agent use
print(result.ir.warnings)       # degradation trail
print(result.ir.metadata)       # OCR confidence, adapter metadata, etc.
print(result.paperlm_json)      # full IR JSON sidecar
print(result.paperlm_chunks_jsonl)  # one text-bearing block per JSONL line
```

### Force a specific engine

```python
from markitdown import MarkItDown

md = MarkItDown(enable_plugins=True, paperlm_engine="ocr")        # force OCR
md = MarkItDown(enable_plugins=True, paperlm_engine="docling")    # skip scanned-check
md = MarkItDown(enable_plugins=True, paperlm_engine="fallback")   # pdfminer only
md = MarkItDown(enable_plugins=True, paperlm_enable_ocr=False)    # disable OCR in auto mode
md = MarkItDown(enable_plugins=True, paperlm_enable_formula=True) # opt-in formula LaTeX extraction
```

### Memory notes

The OCR path uses **PP-OCRv5 mobile** models by default: ~2.7 GB peak RSS,
~15 s / page on CPU, zero measurable quality loss vs server models on our
test corpus (see [benchmarks/phase3_perf.md](benchmarks/phase3_perf.md)).
OCR conversions also populate page-level confidence under
`result.ir.metadata["ocr"]` and add warnings for empty or low-confidence
pages.

For worker machines under 4 GB RAM:

```python
from paperlm.engines.ocr_adapter import OCRAdapter

adapter = OCRAdapter(low_memory=True)   # ~2.0 GB peak, slightly slower
# Or: OCRAdapter(variant="server") for ~10 GB peak — opt-in only
```

For now these flags are exposed only on the Python adapter class; hook
them up via a custom plugin kwargs integration if you need to drive them
from the CLI. Direct `MarkItDown(...)` kwarg support is planned in a
later release.

### Batch/server worker pool

For batch ingestion services, avoid loading Docling/PaddleOCR in the API
process. `DoclingWorkerPool` keeps one MarkItDown instance alive per
worker subprocess, applies per-task timeout/RSS limits, and restarts only
the offending worker on failure.

```python
from paperlm.workers import DoclingWorkerPool

with DoclingWorkerPool(num_workers=2, timeout_s=300, max_rss_mb_hard=6144) as pool:
    results = pool.convert_many(["paper_a.pdf", "paper_b.pdf"])

for result in results:
    print(result.status, result.engine_used, len(result.markdown))
```

This is a Python API for service deployments, not a replacement for the
default `markitdown --use-plugins paper.pdf` CLI path.

### CLI

```bash
markitdown --use-plugins paper.pdf -o paper.md
markitdown --list-plugins        # should show "paperlm"
```

For batch/server ingestion, use `paperlm-batch` so Docling is loaded in
reusable guarded worker subprocesses instead of once per document:

```bash
paperlm-batch paper_a.pdf paper_b.pdf \
  --workers 1 \
  --timeout-s 300 \
  --max-rss-mb-hard 6144 \
  --output-dir outputs/ \
  --output-jsonl outputs/results.jsonl
```

`--output-dir` writes `*.md`, `*.paperlm.json`, and `*.chunks.jsonl`
artifacts. The JSONL result stream stays compact by default; add
`--include-markdown` only if you want full Markdown embedded in each row.

JSONL input is supported for queues and ETL jobs:

```jsonl
{"id": "doc-1", "pdf_path": "paper_a.pdf"}
{"id": "doc-2", "pdf_path": "paper_b.pdf"}
```

```bash
paperlm-batch --input-jsonl jobs.jsonl --output-jsonl results.jsonl --output-dir outputs/
```

### Operational tools

Use `paperlm-tools warmup` during deployment to pre-download and
initialize optional engines before production traffic hits the first
conversion. Warmup runs in guarded worker subprocesses, so timeout/RSS
limits kill only the warmup worker instead of the parent process.

```bash
paperlm-tools warmup --engine docling
paperlm-tools warmup --engine docling,ocr --timeout-s 600 --max-rss-mb-hard 6144
```

The command fails if the requested engine silently falls back to another
engine. For example, `--engine docling` must finish with
`engine_used=docling`; otherwise install `paperlm[docling]` or check the
runtime environment.

## How it works

```
Input PDF
  │
  ▼
EngineRouter (auto mode)
  │
  ├─ sample text layer (scanned_detector.py)
  │
  ├─ if scanned (no text)  →  OCRAdapter (PaddleOCR, Apache-2.0)
  │                            ↓ on empty/fail
  │                            DoclingAdapter (MIT)
  │                            ↓ on empty/fail
  │                            FallbackAdapter (pdfminer)
  │
  └─ if has text layer    →  DoclingAdapter
                              ↓ on empty/fail
                              OCRAdapter (if installed)
                              ↓ on empty/fail
                              FallbackAdapter (pdfminer — shipped as core dep)
  │
  ▼
IR (Block / BlockType / BBox / reading_order)
  │
  ▼
MarkdownSerializer → result.markdown
```

The router is fail-safe **as long as the package is properly installed**:
a real `pip install -e .` pulls pdfminer.six and pdfplumber as core deps,
so the `FallbackAdapter` is always attempted last. If you are running
tests with `PYTHONPATH=src` but **without** actually installing the
package (a common reviewer flow), `pdfminer.six` may be missing — in
that case the router returns an IR with `engine_used="failed"` and
`result.ir.warnings` explaining what happened. No exception propagates
to the caller either way.

## License matrix for optional engines

| Extra | Engine | License | Commercial use |
|---|---|---|---|
| *(core)* | pdfminer.six / pdfplumber | MIT / MIT | ✅ safe |
| `[docling]` **(recommended default)** | Docling 2.90 | **MIT** | ✅ safe |
| `[ocr]` | PaddleOCR + paddlepaddle | Apache-2.0 | ✅ safe |
| `[formula]` *(opt-in)* | pix2tex | MIT | ✅ safe |
| `[marker]` *(optional)* | Marker | GPL-3 + OpenRAIL-M | ⚠️ copyleft; requires Datalab license above $2 M revenue |
| `[mineru]` *(optional)* | MinerU | AGPL | ⚠️ strong copyleft; triggers on network distribution |

Main package is **Apache-2.0** and never transitively pulls GPL/AGPL dependencies unless you opt in.

## Development

```bash
uv venv --python 3.12 ~/.venvs/paperlm
source ~/.venvs/paperlm/bin/activate
export UV_LINK_MODE=copy          # needed when src is on exFAT
uv pip install -e ".[docling,ocr,dev]"

# Fast tests (no ML model loads)
make test-fast

# Slow integration tests (require Docling / PaddleOCR model downloads
# on first run).
pytest tests/test_docling_adapter.py       # needs pip install -e '.[docling]'
pytest tests/test_ocr_adapter.py           # needs pip install -e '.[ocr]'
pytest tests/test_pdf_converter_e2e.py     # needs pdfminer.six + docling
```

**Memory note**: do not run Docling + PaddleOCR tests in the same
pytest process — together they hold ~3 GB of models. Run them
sequentially.

The competitor benchmark is also guarded by default. `make
benchmark-compare` runs only the smoke fixture profile and the core
triad (`MarkItDown`, `paperlm`, Docling), with per-run timeouts, RSS
warnings, and hard RSS limits that kill only the offending subprocess.
For release-facing evidence, `make benchmark-report` writes
`benchmarks/reports/latest.md` and `benchmarks/reports/latest.json`
with quality, reading-order, latency, RSS, and failure summaries across
the current 8-fixture corpus.
Use the full/heavy matrix only when you intentionally want to load every
installed parser:

```bash
make benchmark-report        # release-facing report, core triad, full fixture corpus
make benchmark-compare       # safe smoke profile
make benchmark-compare-full  # opt-in full corpus + Marker/MinerU runners
make benchmark-long-perf     # one long math-heavy PDF, with paperlm timing breakdown
make benchmark-long-profile  # cProfile top 30 for paperlm long-PDF breakdown
make benchmark-worker-pool   # compare fresh subprocesses vs one pooled worker
```

### Reproducing integration evidence without installing every extra

The `fast` test suite deliberately **skips** anything that needs an ML
model or a missing core dep. **That is expected behaviour** — a skipped
test's green state is not a claim that the underlying optional engine
works.

Three progressively stronger ways to verify the integration paths:

1. **Trust pre-recorded evidence** — [`benchmarks/phase4_integration.md`](benchmarks/phase4_integration.md)
   records an 8-fixture sweep on macOS-CPU, one subprocess per fixture.
   All eight converge to non-empty IRs, zero errors, every peak RSS
   ≤ 4 GB.

2. **Run the GitHub Actions `integration` job** on your fork:
   ```bash
   gh workflow run test.yml --field ref=<branch>
   ```
   It fetches fixtures, installs `.[docling,ocr]`, and runs
   `test_docling_adapter.py` / `test_ocr_adapter.py` / `test_pdf_converter_e2e.py`
   on a fresh Linux runner.

3. **Reproduce locally**:
   ```bash
   python tests/fixtures/fetch.py                        # build the corpus
   pip install -e '.[docling,ocr,dev]'
   make test-all                                         # ~3-4 minutes
   python benchmarks/w4d5_integration_sweep.py           # per-fixture peak RSS
   ```

### Test fixtures (not in git — regenerate locally)

The corpus is 8 PDFs covering different layouts, languages, and dense
content (tables, formulas). Rebuild it with one command:

```bash
python tests/fixtures/fetch.py          # download + build everything
python tests/fixtures/fetch.py --check  # verify all present, exit 1 if missing
```

| Fixture | Pages | Character |
|---|---|---|
| `sample_en_two_col.pdf` | 27 | EN double-column bioRxiv bioinfo benchmark |
| `sample_zh_mixed.pdf` | 10 | ZH double-column 《生命科学》2024 review |
| `sample_arxiv_llm_survey.pdf` | 14 | EN survey, moderate tables + figures |
| `sample_arxiv_table_heavy.pdf` | 12 | EN benchmark paper, 5+ tables in first 5p |
| `sample_arxiv_math.pdf` | 86 | EN long, math-heavy (DeepSeek-R1 report) |
| `sample_arxiv_long_ir.pdf` | 60 | EN long single-column survey |
| `sample_scanned.pdf` | 5 | Synthetic — ZH paper rasterized to images |
| `sample_scanned_1p.pdf` | 1 | Synthetic — single page for fast OCR tests |

## Status & roadmap

- ✅ Week 1 — skeleton + Docling integration + IR + Markdown serializer
- ✅ Week 2 — pdfminer fallback + EngineRouter + scanned detection + PaddleOCR
- ✅ Week 3 — formula inline/block detection, table polish, caption linking, reading-order repair
- ✅ Week 4 — coverage, CI, benchmark docs, performance/RSS guardrails
- 🚧 Week 5 — release hardening, TestPyPI/PyPI publication, launch docs

See [`../PRD.md`](../PRD.md) for the full spec.

## License

Apache-2.0. See [LICENSE](LICENSE).
