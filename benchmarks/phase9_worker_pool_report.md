# Phase 9 - Worker Pool Probe

Batch-ingestion probe comparing one fresh worker per PDF vs reusable `DoclingWorkerPool` workers for the whole batch.

Fixtures: `sample_arxiv_table_heavy.pdf`, `sample_zh_mixed.pdf`, `sample_arxiv_llm_survey.pdf`.
Timeout: `900s`; RSS hard-kill threshold: `6144 MB`; pooled workers: `1`.

## Summary

| Mode | Status | OK docs | Total time (s) | Peak RSS (MB) | Median doc time (s) | Total chars | First issue |
|---|---|---|---|---|---|---|---|
| fresh-subprocess | OK | 3/3 | 50.49 | 1787.9 | 16.55 | 145427 | `` |
| pooled-worker | OK | 3/3 | 29.2 | 1758.2 | 11.31 | 145427 | `` |

## Details

| Mode | Fixture | Status | Worker | Time (s) | Peak RSS (MB) | Chars | Blocks | Engine | First line / error |
|---|---|---|---|---|---|---|---|---|---|
| fresh-subprocess | `sample_arxiv_table_heavy.pdf` | OK | 0 | 13.99 | 1369.0 | 54069 | 190 | docling | `# TARGET: Benchmarking Table Retrieval for Generative Tasks` |
| fresh-subprocess | `sample_zh_mixed.pdf` | OK | 0 | 16.55 | 1302.0 | 20470 | 183 | docling | `# Bioinformatics and biomanufacturing: the importance of big biodata and its data mining in b iomanufacturing` |
| fresh-subprocess | `sample_arxiv_llm_survey.pdf` | OK | 0 | 16.74 | 1787.9 | 70888 | 223 | docling | `# Large Language Models in Bioinformatics: A Survey` |
| pooled-worker | `sample_arxiv_table_heavy.pdf` | OK | 0 | 13.08 | 1381.8 | 54069 | 190 | docling | `# TARGET: Benchmarking Table Retrieval for Generative Tasks` |
| pooled-worker | `sample_zh_mixed.pdf` | OK | 0 | 3.67 | 1418.9 | 20470 | 183 | docling | `# Bioinformatics and biomanufacturing: the importance of big biodata and its data mining in b iomanufacturing` |
| pooled-worker | `sample_arxiv_llm_survey.pdf` | OK | 0 | 11.31 | 1758.2 | 70888 | 223 | docling | `# Large Language Models in Bioinformatics: A Survey` |

## Recovery Check

This opt-in check forces the first real worker to exceed a 1 MB RSS limit, then reruns the same PDF with the normal RSS limit.

| Fixture | Forced status | Recovered status | Engine | Recovered chars | Recovered peak RSS (MB) | Error |
|---|---|---|---|---|---|---|
| `sample_arxiv_table_heavy.pdf` | MEMORY_LIMIT | OK | docling | 54069 | 1312.3 | `worker exceeded RSS hard limit 1 MB (peak 7.0 MB)` |

## Observations

- The pooled worker was `1.73x` faster than fresh subprocesses (29.20s vs 50.49s).
- Peak RSS was `1758.2 MB` for pooled-worker vs `1787.9 MB` per fresh worker.
- Pooled worker indices observed: `[0]` across `3` docs, which is the reuse evidence to check when validating batch mode.
- This report used `1` pooled worker(s). Increase `--pool-workers` only after memory headroom is proven.
