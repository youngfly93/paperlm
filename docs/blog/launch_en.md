# paperlm: a scientific-paper PDF to Markdown plugin for MarkItDown

_Published: <DATE when you post>_

## The problem in one screenshot

Microsoft's [MarkItDown](https://github.com/microsoft/markitdown) is a
great all-rounder: point it at a PDF and you get Markdown. For invoices,
forms, and simple reports it works out of the box. For scientific PDFs
it does not — the source code itself admits so:

> *"This function is designed for structured tabular data (like invoices),
> **not for multi-column text layouts in scientific documents**"*
> — `markitdown/packages/markitdown/src/markitdown/converters/_pdf_converter.py:403`

Here is what that looks like on the [TARGET benchmark paper
(arXiv:2505.11545)](https://arxiv.org/abs/2505.11545):

```markdown
|     | TARGET: |     | Benchmarking |     |     | Table | Retrieval | for Generative |     | Tasks |
| --- | ------- | --- | ------------ | --- | --- | ----- | --------- | -------------- | --- | ----- |
XingyuJi*1,ParkerGlenn2,AdityaG.Parameswaran1,MadelonHulsebos3
5202 yaM 41  ]RI.sc[  1v54511.5052:viXra Thedatalandscapeisrichwithstructureddata,
```

The title is mistakenly interpreted as a broken GFM table. The arXiv
watermark (read bottom-to-top: `51 May 2025 [cs.IR]`) becomes inline
text. Author names collapse into a single token. Not usable for LLM
pipelines.

## What paperlm does

`paperlm` is a **drop-in plugin** that replaces MarkItDown's
PDF converter with a layout-aware pipeline:

1. **[Docling 2.90](https://github.com/docling-project/docling)** (MIT) for text PDFs — layout analysis, table extraction, reading-order repair.
2. **[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) PP-OCRv5 mobile** (Apache-2.0) for scanned PDFs — strong Chinese and English recognition.
3. **pdfminer.six** as the always-available fallback.

Same API, new behaviour:

```python
from markitdown import MarkItDown
md = MarkItDown(enable_plugins=True)
print(md.convert("paper.pdf").markdown)
```

The same page above now renders as:

```markdown
## TARGET: Benchmarking Table Retrieval for Generative Tasks

> * Correspondence to madelon.hulsebos@cwi.nl and jixy2012@berkeley.edu

Large Language Models (LLMs) have become an indispensable tool in the
knowledge worker's arsenal...

## 1 Introduction

The data landscape is rich with structured data, often of high value
to organizations...
```

The watermark is stripped. The title gets a proper `##` heading. The
introduction reflows into a paragraph. LLMs can now reason about it.

## Why this is a plugin, not a fork

MarkItDown already ships with a plugin mechanism
(`priority=-1.0` overrides the built-in PDF converter). `markitdown-ocr`
proved the pattern works; `paperlm` just takes it further.

The upside: zero migration. If you are already running MarkItDown, a
`pip install paperlm[docling]` and one flag change
(`enable_plugins=True`) is the entire migration.

## Memory budget

Docling + PaddleOCR sound scary on CPU. They are not, with the right
config:

| Fixture | Engine | Time | Peak RSS |
|---|---|---|---|
| 10-page Chinese paper | Docling | 11 s | 1.4 GB |
| 27-page bioRxiv | Docling | 92 s | 2.3 GB |
| 1-page scanned | PaddleOCR | 16 s | 2.7 GB |

Every fixture in our 8-paper corpus stays under 4 GB. The
[RSS probe report](../../benchmarks/phase4_rss_probe.md) documents how
we got there — TL;DR: PP-OCRv5 *mobile* models are as accurate as
*server* models on Chinese bioinformatics papers, while using 74% less
RAM.

## License story

Only MIT and Apache-2.0 code is installed by default. GPL-3 (Marker) and
AGPL (MinerU) are gated behind opt-in extras with explicit warnings.
You can drop this into a commercial stack without pulling in copyleft.

## What it doesn't do (yet)

- **Bilingual documents** with Chinese + English laid out side-by-side
  on the same page still interleave oddly — a Docling layout-model
  quirk. Most single-language papers are clean.
- **Formula LaTeX extraction** is opt-in
  (`paperlm_enable_formula=True`) because it adds a 500 MB VLM.
- **Figures** are rendered as `![](figure)` placeholders. Image export
  to disk is on the roadmap.

## Get it

- GitHub: `https://github.com/youngfly93/paperlm`
- PyPI: `pip install paperlm[docling]`
- CLI: `markitdown --use-plugins paper.pdf -o paper.md`

Bug reports and PRs welcome.
