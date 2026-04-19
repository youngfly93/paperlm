# Phase 5 — Competitor Comparison

_Multi-dimensional comparison across current scientific-PDF competitors._

Report generated from `markitdown-paperlm` using /Users/yangfei/.venvs/markitdown-paperlm/bin/python.
Profile: `smoke`. Timeout: `360s`. RSS warning threshold: `4096 MB`. RSS hard-kill threshold: `8192 MB`.

## Dimensions

This comparison intentionally splits dimensions into two buckets:

1. **Static product dimensions**: license, commercial constraints, output formats, install surface, and claimed OCR / structure scope.
2. **Empirical conversion dimensions**: success rate, latency, peak memory, output size, heading density, table density, formula markers, and obvious garbage-token leakage.

Run controls:

- profile: `smoke` (3 fixture(s))
- per-tool/per-fixture timeout: `360s`
- RSS warning threshold: `4096 MB`
- RSS hard-kill threshold: `8192 MB`

These automated metrics are useful for triage, but they are **not** a substitute for human review on reading order and semantic faithfulness.

Recommended human review dimensions on top of this report:

- text coverage: is the main body present and readable?
- reading order: are title, authors, abstract, and columns in the right order?
- table usability: did dense tables survive as usable markdown or structured rows?
- scanned OCR quality: is scanned Chinese / English legible enough for RAG?
- formula usability: do equations survive as meaningful inline/block placeholders or LaTeX?

## Static Product Matrix

| Tool | Role | Outputs | OCR / scanned path | License | Commercial note | Install surface |
|---|---|---|---|---|---|---|
| MarkItDown baseline | Generic document-to-Markdown baseline | Markdown | Generic PDF path; can be extended with plugins/add-ons. | MIT | Permissive. PDF support requires optional deps. | Light |
| paperlm | Scientific PDF plugin on top of MarkItDown | Markdown (+ Python-only IR metadata) | Auto routes scanned PDFs to PaddleOCR when installed. | Apache-2.0 | Permissive. Optional extras stay opt-in. | Medium |
| Docling standalone | General-purpose document parser | Markdown, HTML, DocTags, JSON | Built-in OCR and advanced PDF understanding. | MIT | Permissive. Model licenses may differ by component. | Medium |
| Marker | Accuracy-focused document parser | Markdown, JSON, HTML, chunks | OCR if necessary; optional LLM mode for higher accuracy. | GPL code + OpenRAIL-M model weights | Commercial restrictions/caveats above free tier. | Heavy |

### Official References

- **MarkItDown baseline**: https://github.com/microsoft/markitdown
- **paperlm**: https://github.com/youngfly93/paperlm
- **Docling standalone**: https://github.com/docling-project/docling
- **Marker**: https://github.com/VikParuchuri/marker

## Tool Summary

| Tool | Available here | Success / runs | Median time (s) | Median chars | Notes |
|---|---|---|---|---|---|
| MarkItDown baseline | yes | 2/3 | 1.02 | 65979 | best-effort run |
| paperlm | yes | 3/3 | 19.97 | 20470 | best-effort run |
| Docling standalone | yes | 3/3 | 10.22 | 20579 | best-effort run |
| Marker | yes | 1/3 | 75.02 | 20526 | best-effort run |
| MinerU | no | 0/0 | — | — | not installed or runner failed |

## Observed Verdict

These are corpus-specific observations from this run, not universal claims.

- Against raw MarkItDown, `paperlm` was clearly stronger on this corpus: `3/3` successful runs vs `2/3`.
- Scanned PDFs were a hard separator here: raw MarkItDown converted `0/1` scanned fixtures, while `paperlm` converted `1/1`.
- Structural proxies also favored `paperlm`: median headings were `26` vs `0`, while median markdown-table lines were `0` vs `331`. That pattern usually means less table hallucination and better scientific-document structure.
- `paperlm` and raw Docling were competitive on success rate in this run: `3/3` vs `3/3`.
- On median latency, `paperlm` was `19.97s` vs Docling `10.22s`, so the plugin path was slower in this environment.
- `paperlm` produced more title-like first lines on the fixture set (`2` docs starting with a markdown heading vs `1` for Docling). That supports the front-matter normalization layer as a real quality improvement.
- The honest product position from this report is: `paperlm` is already better than baseline MarkItDown for scientific PDFs, but it is not yet uniformly better than raw Docling on text-layer documents.

## Performance Guardrails

| Tool | Fixture | Guardrail | Detail |
|---|---|---|---|
| Marker | `sample_arxiv_table_heavy.pdf` | timeout | worker timed out after 360s |
| Marker | `sample_scanned_1p.pdf` | timeout | worker timed out after 360s |

## Empirical Fixture Matrix

| Tool | Fixture | Status | Time (s) | Peak RSS (MB) | Chars | Headings | Tables | `$$` | `(cid:)` | OCR mean | OCR low pages | First line |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MarkItDown baseline | `sample_arxiv_table_heavy.pdf` | OK | 1.35 | 156.6 | 109044 | 1 | 564 | 0 | 0 | — | — | `\|     \| TARGET: \|     \| Benchmarking \|     \|     \| Table \| Retrieval \| for Generative \|     \| Tasks \|     \|` |
| MarkItDown baseline | `sample_zh_mixed.pdf` | OK | 0.68 | 162.3 | 22915 | 0 | 98 | 0 | 0 | — | — | `第36卷 第11期 生命科学 Vol. 36, No. 11` |
| MarkItDown baseline | `sample_scanned_1p.pdf` | EMPTY | 0.34 | 144.2 | 0 | 0 | 0 | 0 | 0 | — | — | `` |
| paperlm | `sample_arxiv_table_heavy.pdf` | OK | 15.99 | 1627.4 | 54071 | 26 | 50 | 0 | 0 | — | — | `# TARGET: Benchmarking Table Retrieval for Generative Tasks` |
| paperlm | `sample_zh_mixed.pdf` | OK | 19.97 | 1478.6 | 20470 | 38 | 0 | 0 | 0 | — | — | `# Bioinformatics and biomanufacturing: the importance of big biodata and its data mining in b iomanufacturing` |
| paperlm | `sample_scanned_1p.pdf` | OK | 20.6 | 2903.1 | 2548 | 0 | 0 | 0 | 0 | 0.979 | — | `生命科学` |
| Docling standalone | `sample_arxiv_table_heavy.pdf` | OK | 14.08 | 1238.9 | 53402 | 26 | 50 | 0 | 0 | — | — | `## TARGET: Benchmarking Table Retrieval for Generative Tasks` |
| Docling standalone | `sample_zh_mixed.pdf` | OK | 10.22 | 1203.0 | 20579 | 38 | 0 | 0 | 0 | — | — | `文章编号` |
| Docling standalone | `sample_scanned_1p.pdf` | OK | 8.04 | 1069.9 | 2081 | 1 | 0 | 0 | 0 | — | — | `DOI: 10.13376/j.cbls/20240163` |
| Marker | `sample_arxiv_table_heavy.pdf` | TIMEOUT | 360.09 | 1127.0 | — | — | — | — | — | — | — | `worker timed out after 360s` |
| Marker | `sample_zh_mixed.pdf` | OK | 75.02 | 1792.7 | 20526 | 37 | 0 | 0 | 0 | — | — | `DOI: 10.13376/j.cbls/20240163` |
| Marker | `sample_scanned_1p.pdf` | TIMEOUT | 360.15 | 1366.7 | — | — | — | — | — | — | — | `worker timed out after 360s` |

## Fixture Corpus

- `sample_arxiv_table_heavy.pdf` (12p): EN benchmark paper dense with tables (~5 tables in first 5 pages)
- `sample_zh_mixed.pdf` (10p): ZH double-column 《生命科学》2024 bioinformatics review
- `sample_scanned_1p.pdf` (1p): synthetic scanned (1p @ 150dpi)
