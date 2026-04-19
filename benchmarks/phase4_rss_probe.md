# Phase 4 — RSS Probe for PaddleOCR

_Week 4 Day 1 — one-page scanned fixture, isolated subprocesses._

Goal: find a PaddleOCR configuration with peak RSS ≤ 4 GB (PRD §5.1).

| Variant | Wall (s) | Peak RSS (MB) | Text lines | Notes |
|---|---|---|---|---|
| A: baseline (server models, 150 dpi) | 27.01 | ❌ 10345.5 | 45 | |
| B: server + gc + paddle flags | 29.82 | ❌ 10635.7 | 45 | |
| C: mobile models (150 dpi) | 15.45 | ✅ 2674.8 | 45 | |
| D: mobile models (120 dpi) | 14.59 | ✅ 2660.1 | 44 | |
| E: mobile + 120 dpi + gc + paddle flags | 16.27 | ✅ 1961.9 | 44 | |
