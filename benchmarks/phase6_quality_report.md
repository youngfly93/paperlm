# Phase 6 — Text Recall And Reading-Order Probe

_Small, manually curated quality benchmark for release review._

## Method

- Snippet recall checks whether title / abstract / body anchors are present.
- Exact matching uses compact normalized text, so whitespace, markdown punctuation, and hyphens do not dominate the score.
- Reading-order checks use exact snippet positions. If a snippet is only partially matched, ordering is marked as missing.
- This is not a universal text-coverage claim; it is a release guardrail for known representative cases.

## Summary

| Tool | Available | Successful fixtures | Exact snippets | Avg snippet score | Order pass | Median time (s) |
|---|---|---|---|---|---|---|
| paperlm | yes | 4/4 | 11/11 | 1.000 | 2/4 | 25.16 |
| Docling standalone | yes | 4/4 | 10/11 | 0.875 | 1/4 | 19.13 |
| MarkItDown baseline | yes | 3/4 | 6/9 | 0.968 | 0/3 | 1.04 |

## Observed Findings

- `paperlm` recalled `11/11` curated snippets exactly and passed `2/4` reading-order checks.
- Remaining `paperlm` quality gaps: `sample_en_two_col.pdf` has out-of-order anchors; `sample_scanned_1p.pdf` has out-of-order anchors.
- Against raw Docling, snippet recall is effectively tied (`11/11` vs `10/11`), while reading-order checks favor `paperlm` in this run (`2/4` vs `1/4`).
- Against baseline MarkItDown, `paperlm` is stronger on both exact snippets and ordering (`6/9` snippets, `0/3` order checks for baseline).

## Details

| Tool | Fixture | Status | Exact snippets | Avg score | Order | Time (s) | First line / error |
|---|---|---|---|---|---|---|---|
| paperlm | `sample_en_two_col.pdf` | OK | 3/3 | 1.000 | fail | 95.44 | `# A systematic benchmark of bioinformatics methods for single-cell and spatial RNA-seq Nanopore long-read data` |
| paperlm | `sample_arxiv_table_heavy.pdf` | OK | 3/3 | 1.000 | pass | 23.47 | `# TARGET: Benchmarking Table Retrieval for Generative Tasks` |
| paperlm | `sample_zh_mixed.pdf` | OK | 3/3 | 1.000 | pass | 24.93 | `# Bioinformatics and biomanufacturing: the importance of big biodata and its data mining in b iomanufacturing` |
| paperlm | `sample_scanned_1p.pdf` | OK | 2/2 | 1.000 | fail | 25.39 | `生命科学` |
| Docling standalone | `sample_en_two_col.pdf` | OK | 3/3 | 1.000 | pass | 24.57 | `## A systematic benchmark of bioinformatics methods for single-cell and spatial RNA-seq Nanopore long-read data` |
| Docling standalone | `sample_arxiv_table_heavy.pdf` | OK | 3/3 | 1.000 | fail | 25.75 | `## TARGET: Benchmarking Table Retrieval for Generative Tasks` |
| Docling standalone | `sample_zh_mixed.pdf` | OK | 3/3 | 1.000 | fail | 13.69 | `文章编号` |
| Docling standalone | `sample_scanned_1p.pdf` | OK | 1/2 | 0.500 | missing abstract_zh | 7.93 | `DOI: 10.13376/j.cbls/20240163` |
| MarkItDown baseline | `sample_en_two_col.pdf` | OK | 1/3 | 0.905 | missing abstract,introduction | 12.48 | `bioRxiv preprint doi: https://doi.org/10.1101/2025.07.21.665920; this version posted July 25, 2025. The copyright holder for this preprint (` |
| MarkItDown baseline | `sample_arxiv_table_heavy.pdf` | OK | 2/3 | 1.000 | missing abstract | 1.04 | `\| \| TARGET: \| \| Benchmarking \| \| \| Table \| Retrieval \| for Generative \| \| Tasks \| \|` |
| MarkItDown baseline | `sample_zh_mixed.pdf` | OK | 3/3 | 1.000 | fail | 0.64 | `第36卷 第11期 生命科学 Vol. 36, No. 11` |
| MarkItDown baseline | `sample_scanned_1p.pdf` | EMPTY | — | — | — | 0.3 | `` |

## Reference Snippets

### `sample_en_two_col.pdf`

- `title`: A systematic benchmark of bioinformatics methods for single-cell and spatial RNA-seq Nanopore long-read data
- `abstract`: Alternative splicing plays a crucial role in transcriptomic complexity
- `introduction`: Alternative splicing significantly contributes to transcriptome complexity

### `sample_arxiv_table_heavy.pdf`

- `title`: TARGET: Benchmarking Table Retrieval for Generative Tasks
- `abstract`: Large Language Models LLMs have become an indispensable tool
- `introduction`: The data landscape is rich with structured data

### `sample_zh_mixed.pdf`

- `title_en`: Bioinformatics and biomanufacturing: the importance of big biodata
- `abstract_zh`: 生物信息学在生物制造中发挥着举足轻重的作用
- `section_1`: 生物制造及其关键特点

### `sample_scanned_1p.pdf`

- `title_en`: Bioinformatics and biomanufacturing: the importance of big biodata
- `abstract_zh`: 生物信息学在生物制造中发挥着举足轻重的作用

