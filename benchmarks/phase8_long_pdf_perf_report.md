# Phase 8 - Long PDF Performance Probe

Targeted long-document profiling. Formula LaTeX enrichment is off by default.

Timeout per subprocess: `900s`; RSS hard-kill threshold: `6144 MB`.
CPU profiling: `off`; profile rows: `30`.

## Summary

| Tool | Status | Time (s) | Peak RSS (MB) | Chars | Blocks | `$$` | First line / error |
|---|---|---|---|---|---|---|---|
| Docling standalone | OK | 34.45 | 3007.1 | 241375 | - | 0 | `<!-- image -->` |
| paperlm breakdown | OK | 35.55 | 3032.4 | 240647 | 903 | 2 | `# DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning` |

## PaperLM Breakdown

### paperlm breakdown

| Step | Time (s) | Share |
|---|---|---|
| `scanned_check` | 0.149 | 0.4% |
| `docling_init` | 1.246 | 3.7% |
| `docling_convert` | 31.975 | 95.8% |
| `ir_postprocess` | 0.015 | 0.0% |
| `markdown_render` | 0.000 | 0.0% |
| `json_sidecars` | 0.003 | 0.0% |

## Observations

- `paperlm` was `1.03x` Docling standalone on this fixture (35.55s vs 34.45s).
