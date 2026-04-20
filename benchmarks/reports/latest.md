# paperlm Benchmark Report

Generated: `2026-04-20T00:52:32.222834+00:00`
Profile: `quality`
Tools: `paperlm_plugin`, `markitdown_baseline`, `docling_standalone`

## Executive Summary

- paperlm succeeded on 4/4 runs vs MarkItDown baseline 3/4.
- On curated snippets, paperlm hit 10/11 exactly vs baseline 6/9.
- Against Docling, paperlm order checks were 2/4 vs 1/4.
- Median latency was paperlm 9.30s vs Docling 8.96s.

## Corpus

- `sample_en_two_col.pdf` (27p): EN double-column bioRxiv bioinformatics benchmark paper
- `sample_arxiv_table_heavy.pdf` (12p): EN benchmark paper dense with tables (~5 tables in first 5 pages)
- `sample_zh_mixed.pdf` (10p): ZH double-column 《生命科学》2024 bioinformatics review
- `sample_scanned_1p.pdf` (1p): synthetic scanned (1p @ 150dpi)

## Tool Summary

| Tool | Available | Success | Median time (s) | Median RSS (MB) | Exact snippets | Avg score | Order pass |
|---|---|---|---|---|---|---|---|
| paperlm | yes | 4/4 | 9.3 | 1376.6 | 10/11 | 0.875 | 2/4 |
| MarkItDown baseline | yes | 3/4 | 0.82 | 228.1 | 6/9 | 0.968 | 0/3 |
| Docling standalone | yes | 4/4 | 8.965 | 1330 | 10/11 | 0.875 | 1/4 |

## Quality Matrix

| Tool | Fixture | Status | Engine | First line title-like | Exact snippets | Avg score | Order | First line / error |
|---|---|---|---|---|---|---|---|---|
| paperlm | `sample_en_two_col.pdf` | OK | docling | yes | 3/3 | 1 | fail | `# A systematic benchmark of bioinformatics methods for single-cell and spatial RNA-seq Nanopore long-read data` |
| paperlm | `sample_arxiv_table_heavy.pdf` | OK | docling | yes | 3/3 | 1 | pass | `# TARGET: Benchmarking Table Retrieval for Generative Tasks` |
| paperlm | `sample_zh_mixed.pdf` | OK | docling | yes | 3/3 | 1 | pass | `# Bioinformatics and biomanufacturing: the importance of big biodata and its data mining in b iomanufacturing` |
| paperlm | `sample_scanned_1p.pdf` | OK | docling | yes | 1/2 | 0.5 | missing abstract_zh | `# Bioinformatics and biomanufacturing: the importance of big biodata and its data mining in biomanufacturing` |
| MarkItDown baseline | `sample_en_two_col.pdf` | OK | markitdown | no | 1/3 | 0.905 | missing abstract,introduction | `bioRxiv preprint doi: https://doi.org/10.1101/2025.07.21.665920; this version posted July 25, 2025. The copyright holder for this preprint (which` |
| MarkItDown baseline | `sample_arxiv_table_heavy.pdf` | OK | markitdown | no | 2/3 | 1 | missing abstract | `\| \| TARGET: \| \| Benchmarking \| \| \| Table \| Retrieval \| for Generative \| \| Tasks \| \|` |
| MarkItDown baseline | `sample_zh_mixed.pdf` | OK | markitdown | no | 3/3 | 1 | fail | `DOI: 10.13376/j.cbls/20240163` |
| MarkItDown baseline | `sample_scanned_1p.pdf` | EMPTY | — | — | — | — | — | `empty markdown` |
| Docling standalone | `sample_en_two_col.pdf` | OK | docling | yes | 3/3 | 1 | pass | `## A systematic benchmark of bioinformatics methods for single-cell and spatial RNA-seq Nanopore long-read data` |
| Docling standalone | `sample_arxiv_table_heavy.pdf` | OK | docling | yes | 3/3 | 1 | fail | `## TARGET: Benchmarking Table Retrieval for Generative Tasks` |
| Docling standalone | `sample_zh_mixed.pdf` | OK | docling | no | 3/3 | 1 | fail | `文章编号` |
| Docling standalone | `sample_scanned_1p.pdf` | OK | docling | no | 1/2 | 0.5 | missing abstract_zh | `DOI: 10.13376/j.cbls/20240163` |

## Performance Matrix

| Tool | Fixture | Status | Time (s) | Peak RSS (MB) | Chars | Lines | Headings | Tables | `$$` | `(cid:)` | OCR mean | OCR low pages |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| paperlm | `sample_en_two_col.pdf` | OK | 19.1 | 2405.2 | 125624 | 926 | 53 | 50 | 0 | 0 | — | — |
| paperlm | `sample_arxiv_table_heavy.pdf` | OK | 11.25 | 1468.1 | 54069 | 424 | 26 | 50 | 0 | 0 | — | — |
| paperlm | `sample_zh_mixed.pdf` | OK | 7.35 | 1285.1 | 20470 | 365 | 38 | 0 | 0 | 0 | — | — |
| paperlm | `sample_scanned_1p.pdf` | OK | 5.45 | 1098.7 | 2081 | 23 | 1 | 0 | 0 | 0 | — | — |
| MarkItDown baseline | `sample_en_two_col.pdf` | OK | 10.82 | 974.4 | 223864 | 2146 | 0 | 830 | 0 | 1 | — | — |
| MarkItDown baseline | `sample_arxiv_table_heavy.pdf` | OK | 0.82 | 228.1 | 109044 | 1151 | 1 | 564 | 0 | 0 | — | — |
| MarkItDown baseline | `sample_zh_mixed.pdf` | OK | 0.67 | 190 | 21092 | 1291 | 0 | 0 | 0 | 0 | — | — |
| MarkItDown baseline | `sample_scanned_1p.pdf` | EMPTY | 0.23 | 136.9 | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| Docling standalone | `sample_en_two_col.pdf` | OK | 17.06 | 2355 | 122153 | 850 | 53 | 50 | 0 | 0 | — | — |
| Docling standalone | `sample_arxiv_table_heavy.pdf` | OK | 10.62 | 1413.5 | 53400 | 410 | 26 | 50 | 0 | 0 | — | — |
| Docling standalone | `sample_zh_mixed.pdf` | OK | 7.31 | 1246.5 | 20579 | 327 | 38 | 0 | 0 | 0 | — | — |
| Docling standalone | `sample_scanned_1p.pdf` | OK | 5.66 | 1083.9 | 2081 | 23 | 1 | 0 | 0 | 0 | — | — |

## Failure / Guardrails

| Tool | Fixture | Guardrail | Detail |
|---|---|---|---|
| MarkItDown baseline | `sample_scanned_1p.pdf` | empty | empty markdown |

## Interpretation

- This report is corpus-specific evidence, not a universal accuracy claim.
- Snippet recall checks curated anchors, not complete full-document ground truth.
- Reading-order pass requires exact anchor matches; partial matches are marked missing.
- Marker and MinerU are intentionally opt-in because their installs and model stacks are heavy.

