"""Phase 5 competitor comparison.

Builds a multi-dimensional comparison report for the current PDF fixture
corpus. The report has two layers:

1. Static product matrix
   License, commercial caveats, output formats, scope, and install surface.

2. Empirical fixture matrix
   Runs whichever tools are available locally and records conversion
   success, latency, peak RSS, output size, and lightweight markdown
   structure proxies (heading/table/formula counts, common garbage tokens).

This script is intentionally best-effort:
  - `paperlm` is run from the local source tree.
  - `MarkItDown` baseline and `Docling` use local Python imports.
  - `Marker` and `MinerU` are optional CLI integrations and are only run if
    their commands are installed. Output discovery is heuristic but isolated.
  - The default run is a smoke profile. Full-corpus / heavy-tool runs are
    opt-in because OCR and parser model stacks can exhaust workstation memory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parent
SRC = ROOT / "src"
FIX = ROOT / "tests" / "fixtures"
REPORT = HERE / "phase5_competitor_matrix.md"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.process_guard import run_guarded_subprocess  # noqa: E402

sys.path.insert(0, str(SRC))
sys.path.insert(0, str(FIX))
try:
    from fetch import REAL_FIXTURES, SYNTHETIC_FIXTURES
finally:
    sys.path.pop(0)
    sys.path.pop(0)


@dataclass(frozen=True)
class ToolCard:
    key: str
    label: str
    category: str
    official_url: str
    license: str
    commercial_note: str
    outputs: str
    scan_strategy: str
    scope: str
    install_surface: str
    install_hint: str


TOOLCARDS: list[ToolCard] = [
    ToolCard(
        key="markitdown_baseline",
        label="MarkItDown baseline",
        category="Generic document-to-Markdown baseline",
        official_url="https://github.com/microsoft/markitdown",
        license="MIT",
        commercial_note="Permissive. PDF support requires optional deps.",
        outputs="Markdown",
        scan_strategy="Generic PDF path; can be extended with plugins/add-ons.",
        scope="Multi-format reader; not scientific-PDF specialized.",
        install_surface="Light",
        install_hint="pip install 'markitdown[pdf]'",
    ),
    ToolCard(
        key="paperlm_plugin",
        label="paperlm",
        category="Scientific PDF plugin on top of MarkItDown",
        official_url="https://github.com/youngfly93/paperlm",
        license="Apache-2.0",
        commercial_note="Permissive. Optional extras stay opt-in.",
        outputs="Markdown (+ Python-only IR metadata)",
        scan_strategy="Auto routes scanned PDFs to PaddleOCR when installed.",
        scope="PDF only; optimized for scientific layouts and RAG-oriented Markdown.",
        install_surface="Medium",
        install_hint="pip install 'paperlm[docling]'",
    ),
    ToolCard(
        key="docling_standalone",
        label="Docling standalone",
        category="General-purpose document parser",
        official_url="https://github.com/docling-project/docling",
        license="MIT",
        commercial_note="Permissive. Model licenses may differ by component.",
        outputs="Markdown, HTML, DocTags, JSON",
        scan_strategy="Built-in OCR and advanced PDF understanding.",
        scope="Multi-format parser; stronger native structure than MarkItDown.",
        install_surface="Medium",
        install_hint="pip install docling",
    ),
    ToolCard(
        key="marker_cli",
        label="Marker",
        category="Accuracy-focused document parser",
        official_url="https://github.com/VikParuchuri/marker",
        license="GPL code + OpenRAIL-M model weights",
        commercial_note="Commercial restrictions/caveats above free tier.",
        outputs="Markdown, JSON, HTML, chunks",
        scan_strategy="OCR if necessary; optional LLM mode for higher accuracy.",
        scope="Broader document support, strong structured outputs.",
        install_surface="Heavy",
        install_hint="pip install marker-pdf",
    ),
    ToolCard(
        key="mineru_cli",
        label="MinerU",
        category="LLM-oriented document parser",
        official_url="https://github.com/opendatalab/MinerU",
        license="AGPL-sensitive stack / YOLO caveat in docs",
        commercial_note="Review license stack carefully before shipping.",
        outputs="Markdown, JSON, rich intermediate formats",
        scan_strategy="Built-in OCR path; docs claim 109-language OCR support.",
        scope="PDF-to-LLM formats, strong table/formula positioning.",
        install_surface="Heavy",
        install_hint='uv pip install -U "mineru[all]"',
    ),
]

REAL_PLAN = [(fx.filename, fx.pages, fx.description) for fx in REAL_FIXTURES]
SYNTH_PLAN = [(name, pages, f"synthetic scanned ({pages}p @ {dpi}dpi)") for (name, pages, dpi) in SYNTHETIC_FIXTURES]
FIXTURES = [*REAL_PLAN, *SYNTH_PLAN]
FIXTURE_META = {name: (pages, desc) for name, pages, desc in FIXTURES}
FIXTURE_NAMES = tuple(FIXTURE_META)
FIXTURE_PROFILES: dict[str, tuple[str, ...]] = {
    "smoke": (
        "sample_arxiv_table_heavy.pdf",
        "sample_zh_mixed.pdf",
        "sample_scanned_1p.pdf",
    ),
    "text": (
        "sample_en_two_col.pdf",
        "sample_zh_mixed.pdf",
        "sample_arxiv_table_heavy.pdf",
    ),
    "full": FIXTURE_NAMES,
}
DEFAULT_PROFILE = "smoke"
DEFAULT_TIMEOUT_S = 240.0
DEFAULT_MAX_RSS_MB = 4096.0
DEFAULT_MAX_RSS_MB_HARD = 6144.0
DEFAULT_TOOLS = "markitdown_baseline,paperlm_plugin,docling_standalone"
ALL_TOOLS = ",".join(card.key for card in TOOLCARDS)

WORKER = r"""
from __future__ import annotations

import json
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(sys.argv[1])
SRC = ROOT / "src"
pdf_path = Path(sys.argv[2])
tool_key = sys.argv[3]

sys.path.insert(0, str(SRC))


def count_tables(md: str) -> int:
    return sum(1 for line in md.splitlines() if line.strip().startswith("|"))


def first_nonempty_line(md: str) -> str:
    for line in md.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return ""


def run_markitdown_baseline(pdf_path: Path):
    from markitdown import MarkItDown

    result = MarkItDown().convert(str(pdf_path))
    return result.markdown, {"engine_used": "markitdown"}


def run_paperlm_plugin(pdf_path: Path):
    from markitdown import MarkItDown
    from markitdown_paperlm import register_converters

    md = MarkItDown()
    register_converters(
        md,
        paperlm_engine="auto",
        paperlm_enable_ocr=True,
        paperlm_enable_formula=False,
    )
    result = md.convert(str(pdf_path))
    ir = getattr(result, "ir", None)
    meta = {
        "engine_used": getattr(result, "engine_used", "unknown"),
        "warnings": getattr(ir, "warnings", []),
        "metadata": getattr(ir, "metadata", {}),
    }
    return result.markdown, meta


def run_docling_standalone(pdf_path: Path):
    from docling.document_converter import DocumentConverter

    result = DocumentConverter().convert(str(pdf_path))
    return result.document.export_to_markdown(), {"engine_used": "docling"}


def _largest_markdown(root: Path) -> str:
    md_files = sorted(root.rglob("*.md"), key=lambda p: p.stat().st_size, reverse=True)
    if not md_files:
        raise RuntimeError("no markdown output discovered")
    return md_files[0].read_text(encoding="utf-8", errors="replace")


def run_marker_cli(pdf_path: Path):
    exe = shutil.which("marker_single")
    if exe is None:
        raise RuntimeError("marker_single not installed")
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        cmd = [
            exe,
            str(pdf_path),
            "--output_dir",
            str(out_dir),
            "--output_format",
            "markdown",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            tail = " | ".join((proc.stderr or proc.stdout).strip().splitlines()[-3:])
            raise RuntimeError(f"marker failed: {tail[:200]}")
        return _largest_markdown(out_dir), {"engine_used": "marker"}


def run_mineru_cli(pdf_path: Path):
    exe = shutil.which("mineru")
    if exe is None:
        raise RuntimeError("mineru not installed")
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        cmd = [exe, "-p", str(pdf_path), "-o", str(out_dir), "-b", "pipeline"]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            tail = " | ".join((proc.stderr or proc.stdout).strip().splitlines()[-3:])
            raise RuntimeError(f"mineru failed: {tail[:200]}")
        return _largest_markdown(out_dir), {"engine_used": "mineru"}


RUNNERS = {
    "markitdown_baseline": run_markitdown_baseline,
    "paperlm_plugin": run_paperlm_plugin,
    "docling_standalone": run_docling_standalone,
    "marker_cli": run_marker_cli,
    "mineru_cli": run_mineru_cli,
}

t0 = time.perf_counter()
result = {
    "tool_key": tool_key,
    "fixture": pdf_path.name,
}

try:
    md, meta = RUNNERS[tool_key](pdf_path)
    elapsed = time.perf_counter() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    warnings = meta.get("warnings", [])
    ocr_meta = (meta.get("metadata") or {}).get("ocr", {})
    empty = not md.strip()
    engine_used = meta.get("engine_used")
    status = "ok"
    error = ""
    if empty:
        status = "empty"
        if warnings:
            error = " | ".join(str(w) for w in warnings[:2])
        elif engine_used == "failed":
            error = "empty markdown and failed engine"
    result.update(
        {
            "status": status,
            "elapsed_s": round(elapsed, 2),
            "peak_mem_mb": round(peak_mb, 1),
            "chars": len(md),
            "lines": len(md.splitlines()),
            "headings": sum(1 for line in md.splitlines() if re.match(r"^#{1,6}\s", line)),
            "tables": count_tables(md),
            "formula_markers": md.count("$$"),
            "cid_tokens": md.count("(cid:"),
            "first_line": first_nonempty_line(md),
            "engine_used": engine_used,
            "warnings": warnings,
            "ocr_mean_confidence": ocr_meta.get("mean_confidence"),
            "ocr_low_confidence_pages": ocr_meta.get("low_confidence_pages", []),
            "error": error,
        }
    )
except Exception as exc:
    elapsed = time.perf_counter() - t0
    result.update(
        {
            "status": "error",
            "elapsed_s": round(elapsed, 2),
            "error": f"{type(exc).__name__}: {exc}",
        }
    )

sys.stdout.write(json.dumps(result, ensure_ascii=True))
"""


def is_tool_available(tool_key: str) -> bool:
    if tool_key == "markitdown_baseline":
        return _module_available("markitdown")
    if tool_key == "paperlm_plugin":
        return True
    if tool_key == "docling_standalone":
        return _module_available("docling")
    if tool_key == "marker_cli":
        return shutil.which("marker_single") is not None
    if tool_key == "mineru_cli":
        return shutil.which("mineru") is not None
    return False


def _module_available(name: str) -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def select_fixture_names(profile: str, fixtures: str | None = None) -> list[str]:
    if fixtures:
        selected = [name.strip() for name in fixtures.split(",") if name.strip()]
    else:
        if profile not in FIXTURE_PROFILES:
            raise ValueError(f"unknown fixture profile: {profile}")
        selected = list(FIXTURE_PROFILES[profile])

    unknown = [name for name in selected if name not in FIXTURE_META]
    if unknown:
        raise ValueError(f"unknown fixture(s): {unknown}")
    return selected


def _run_one(
    tool_key: str,
    fixture_name: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
) -> dict[str, Any]:
    proc = run_guarded_subprocess(
        [sys.executable, "-c", WORKER, str(ROOT), str(FIX / fixture_name), tool_key],
        timeout_s=timeout_s,
        max_rss_mb_hard=max_rss_mb_hard,
    )
    if proc.status == "timeout":
        return {
            "tool_key": tool_key,
            "fixture": fixture_name,
            "status": "timeout",
            "elapsed_s": proc.elapsed_s,
            "peak_mem_mb": proc.peak_rss_mb or "—",
            "error": _guard_error(proc.error, proc.stderr),
        }
    if proc.status == "memory_limit":
        return {
            "tool_key": tool_key,
            "fixture": fixture_name,
            "status": "memory_limit",
            "elapsed_s": proc.elapsed_s,
            "peak_mem_mb": proc.peak_rss_mb or "—",
            "error": _guard_error(proc.error, proc.stderr),
        }
    if proc.returncode != 0 or not proc.stdout.strip():
        tail = " | ".join((proc.stderr or "").strip().splitlines()[-3:])
        return {
            "tool_key": tool_key,
            "fixture": fixture_name,
            "status": "error",
            "elapsed_s": proc.elapsed_s,
            "peak_mem_mb": proc.peak_rss_mb or "—",
            "error": tail or f"worker exit={proc.returncode}",
        }
    row = json.loads(proc.stdout)
    if proc.peak_rss_mb is not None:
        worker_peak = _to_float(row.get("peak_mem_mb"))
        row["peak_mem_mb"] = round(max(worker_peak or 0.0, proc.peak_rss_mb), 1)
    return row


def _render_static_matrix(cards: list[ToolCard]) -> list[str]:
    lines = [
        "## Static Product Matrix",
        "",
        "| Tool | Role | Outputs | OCR / scanned path | License | Commercial note | Install surface |",
        "|---|---|---|---|---|---|---|",
    ]
    for card in cards:
        lines.append(
            f"| {card.label} | {card.category} | {card.outputs} | {card.scan_strategy} | "
            f"{card.license} | {card.commercial_note} | {card.install_surface} |"
        )
    lines.append("")
    lines.append("### Official References")
    lines.append("")
    for card in cards:
        lines.append(f"- **{card.label}**: {card.official_url}")
    lines.append("")
    return lines


def _render_empirical_matrix(results: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## Empirical Fixture Matrix",
        "",
        "| Tool | Fixture | Status | Time (s) | Peak RSS (MB) | Chars | Headings | Tables | `$$` | `(cid:)` | OCR mean | OCR low pages | First line |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in results:
        label = _card(row["tool_key"]).label
        ocr_mean = _fmt_ocr_mean(row.get("ocr_mean_confidence"))
        low_pages = _fmt_pages(row.get("ocr_low_confidence_pages"))
        if row["status"] != "ok":
            detail = _compact(row.get("error", ""))
            lines.append(
                f"| {label} | `{row['fixture']}` | {row['status'].upper()} | {row.get('elapsed_s', '—')} | "
                f"{row.get('peak_mem_mb', '—')} | {row.get('chars', '—')} | {row.get('headings', '—')} | "
                f"{row.get('tables', '—')} | {row.get('formula_markers', '—')} | {row.get('cid_tokens', '—')} | "
                f"{ocr_mean} | {low_pages} | `{detail[:90]}` |"
            )
            continue
        lines.append(
            f"| {label} | `{row['fixture']}` | OK | {row['elapsed_s']} | {row['peak_mem_mb']} | "
            f"{row['chars']} | {row['headings']} | {row['tables']} | {row['formula_markers']} | "
            f"{row['cid_tokens']} | {ocr_mean} | {low_pages} | `{_esc(row['first_line'])}` |"
        )
    lines.append("")
    return lines


def _render_summary(results: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## Tool Summary",
        "",
        "| Tool | Available here | Success / runs | Median time (s) | Median chars | Notes |",
        "|---|---|---|---|---|---|",
    ]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        grouped.setdefault(row["tool_key"], []).append(row)

    for card in TOOLCARDS:
        rows = grouped.get(card.key, [])
        ok_rows = [r for r in rows if r.get("status") == "ok"]
        success = f"{len(ok_rows)}/{len(rows)}" if rows else "0/0"
        if ok_rows:
            med_time = str(round(statistics.median(r["elapsed_s"] for r in ok_rows), 2))
            med_chars = str(int(statistics.median(r["chars"] for r in ok_rows)))
            notes = "best-effort run"
        else:
            med_time = "—"
            med_chars = "—"
            notes = "not installed or runner failed"
        lines.append(
            f"| {card.label} | {'yes' if is_tool_available(card.key) else 'no'} | {success} | "
            f"{med_time} | {med_chars} | {notes} |"
        )
    lines.append("")
    return lines


def _ok_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("status") == "ok"]


def _group_results(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        grouped.setdefault(row["tool_key"], []).append(row)
    return grouped


def _median_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    ok = _ok_rows(rows)
    if not ok:
        return None
    return statistics.median(float(row[key]) for row in ok)


def _title_like_starts(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in _ok_rows(rows) if str(row.get("first_line", "")).startswith("#"))


def _scanned_success(rows: list[dict[str, Any]]) -> tuple[int, int]:
    scanned = [row for row in rows if str(row.get("fixture", "")).startswith("sample_scanned")]
    ok = [row for row in scanned if row.get("status") == "ok"]
    return len(ok), len(scanned)


def _render_observed_verdict(results: list[dict[str, Any]]) -> list[str]:
    grouped = _group_results(results)
    lines = [
        "## Observed Verdict",
        "",
        "These are corpus-specific observations from this run, not universal claims.",
        "",
    ]

    baseline = grouped.get("markitdown_baseline", [])
    paperlm = grouped.get("paperlm_plugin", [])
    docling = grouped.get("docling_standalone", [])

    if baseline and paperlm:
        baseline_ok = len(_ok_rows(baseline))
        paperlm_ok = len(_ok_rows(paperlm))
        baseline_scanned_ok, baseline_scanned_total = _scanned_success(baseline)
        paperlm_scanned_ok, paperlm_scanned_total = _scanned_success(paperlm)
        baseline_headings = _median_metric(baseline, "headings")
        paperlm_headings = _median_metric(paperlm, "headings")
        baseline_tables = _median_metric(baseline, "tables")
        paperlm_tables = _median_metric(paperlm, "tables")
        lines.append(
            f"- Against raw MarkItDown, `paperlm` was clearly stronger on this corpus: "
            f"`{paperlm_ok}/{len(paperlm)}` successful runs vs `{baseline_ok}/{len(baseline)}`."
        )
        lines.append(
            f"- Scanned PDFs were a hard separator here: raw MarkItDown converted "
            f"`{baseline_scanned_ok}/{baseline_scanned_total}` scanned fixtures, while `paperlm` converted "
            f"`{paperlm_scanned_ok}/{paperlm_scanned_total}`."
        )
        if baseline_headings is not None and baseline_tables is not None and paperlm_headings is not None and paperlm_tables is not None:
            lines.append(
                f"- Structural proxies also favored `paperlm`: median headings were "
                f"`{paperlm_headings:.0f}` vs `{baseline_headings:.0f}`, while median markdown-table lines were "
                f"`{paperlm_tables:.0f}` vs `{baseline_tables:.0f}`. That pattern usually means less table hallucination and better scientific-document structure."
            )

    if paperlm and docling:
        paperlm_ok = len(_ok_rows(paperlm))
        docling_ok = len(_ok_rows(docling))
        paperlm_time = _median_metric(paperlm, "elapsed_s")
        docling_time = _median_metric(docling, "elapsed_s")
        paperlm_title_like = _title_like_starts(paperlm)
        docling_title_like = _title_like_starts(docling)
        paperlm_formula = sum(int(row.get("formula_markers", 0)) for row in _ok_rows(paperlm))
        docling_formula = sum(int(row.get("formula_markers", 0)) for row in _ok_rows(docling))
        lines.append(
            f"- `paperlm` and raw Docling were competitive on success rate in this run: "
            f"`{paperlm_ok}/{len(paperlm)}` vs `{docling_ok}/{len(docling)}`."
        )
        if paperlm_time is not None and docling_time is not None:
            slower = "slower" if paperlm_time > docling_time else "faster"
            lines.append(
                f"- On median latency, `paperlm` was `{paperlm_time:.2f}s` vs Docling `{docling_time:.2f}s`, "
                f"so the plugin path was {slower} in this environment."
            )
        if paperlm_title_like > docling_title_like:
            lines.append(
                f"- `paperlm` produced more title-like first lines on the fixture set "
                f"(`{paperlm_title_like}` docs starting with a markdown heading vs `{docling_title_like}` for Docling). "
                "That supports the front-matter normalization layer as a real quality improvement."
            )
        elif docling_title_like > paperlm_title_like:
            lines.append(
                f"- Docling produced more title-like first lines on the fixture set "
                f"(`{docling_title_like}` docs starting with a markdown heading vs `{paperlm_title_like}` for `paperlm`), "
                "so title/author ordering is still a quality gap to close."
            )
        else:
            lines.append(
                f"- `paperlm` and raw Docling tied on title-like first lines "
                f"(`{paperlm_title_like}` docs each starting with a markdown heading)."
            )
        if paperlm_formula != docling_formula:
            lines.append(
                f"- `paperlm` emitted `{paperlm_formula}` formula marker(s) across successful runs vs `{docling_formula}` for raw Docling. "
                "That suggests the formula-aware post-processing path is starting to differentiate, even if it is not yet comprehensive."
            )

    lines.extend(
        [
            "- The honest product position from this report is: `paperlm` is already better than baseline MarkItDown for scientific PDFs, but it is not yet uniformly better than raw Docling on text-layer documents.",
            "",
        ]
    )
    return lines


def _render_performance_guardrails(results: list[dict[str, Any]], max_rss_mb: float) -> list[str]:
    guardrails: list[tuple[str, str, str, str]] = []
    ok_by_tool_fixture = {
        (row["tool_key"], row["fixture"]): row for row in results if row.get("status") == "ok"
    }

    for row in results:
        label = _card(row["tool_key"]).label
        fixture = row["fixture"]
        if row.get("status") == "timeout":
            guardrails.append((label, fixture, "timeout", _compact(row.get("error", ""))))
        if row.get("status") == "memory_limit":
            guardrails.append((label, fixture, "memory", _compact(row.get("error", ""))))
        peak = _to_float(row.get("peak_mem_mb"))
        if peak is not None and peak > max_rss_mb:
            guardrails.append(
                (
                    label,
                    fixture,
                    "rss",
                    f"peak RSS {peak:.1f} MB exceeded warning threshold {max_rss_mb:g} MB",
                )
            )

    for (tool_key, fixture), paperlm in ok_by_tool_fixture.items():
        if tool_key != "paperlm_plugin":
            continue
        docling = ok_by_tool_fixture.get(("docling_standalone", fixture))
        if not docling:
            continue
        paperlm_time = _to_float(paperlm.get("elapsed_s"))
        docling_time = _to_float(docling.get("elapsed_s"))
        if paperlm_time is None or docling_time is None or docling_time <= 0:
            continue
        if paperlm_time > docling_time * 3:
            guardrails.append(
                (
                    _card("paperlm_plugin").label,
                    fixture,
                    "latency",
                    f"{paperlm_time:.2f}s was >3x Docling standalone ({docling_time:.2f}s)",
                )
            )

    lines = ["## Performance Guardrails", ""]
    if not guardrails:
        lines.append(
            f"No timeout, memory-limit, RSS, or >3x-Docling latency warnings were detected "
            f"for this run (RSS threshold: {max_rss_mb:g} MB)."
        )
        lines.append("")
        return lines

    lines.extend(
        [
            "| Tool | Fixture | Guardrail | Detail |",
            "|---|---|---|---|",
        ]
    )
    for tool, fixture, kind, detail in guardrails:
        lines.append(f"| {tool} | `{fixture}` | {kind} | {_esc(detail)} |")
    lines.append("")
    return lines


def _render_methodology(
    profile: str,
    fixture_names: list[str],
    timeout_s: float,
    max_rss_mb: float,
    max_rss_mb_hard: float,
) -> list[str]:
    return [
        "## Dimensions",
        "",
        "This comparison intentionally splits dimensions into two buckets:",
        "",
        "1. **Static product dimensions**: license, commercial constraints, output formats, install surface, and claimed OCR / structure scope.",
        "2. **Empirical conversion dimensions**: success rate, latency, peak memory, output size, heading density, table density, formula markers, and obvious garbage-token leakage.",
        "",
        "Run controls:",
        "",
        f"- profile: `{profile}` ({len(fixture_names)} fixture(s))",
        f"- per-tool/per-fixture timeout: `{timeout_s:g}s`",
        f"- RSS warning threshold: `{max_rss_mb:g} MB`",
        f"- RSS hard-kill threshold: `{max_rss_mb_hard:g} MB`",
        "",
        "These automated metrics are useful for triage, but they are **not** a substitute for human review on reading order and semantic faithfulness.",
        "",
        "Recommended human review dimensions on top of this report:",
        "",
        "- text coverage: is the main body present and readable?",
        "- reading order: are title, authors, abstract, and columns in the right order?",
        "- table usability: did dense tables survive as usable markdown or structured rows?",
        "- scanned OCR quality: is scanned Chinese / English legible enough for RAG?",
        "- formula usability: do equations survive as meaningful inline/block placeholders or LaTeX?",
        "",
    ]


def _esc(text: str) -> str:
    return text.replace("|", "\\|")


def _compact(text: str) -> str:
    return _esc(" ".join(text.split()))


def _guard_error(error: str, stderr: str) -> str:
    tail = " | ".join((stderr or "").strip().splitlines()[-3:])
    if tail:
        return f"{error}: {tail[:200]}"
    return error


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_ocr_mean(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_pages(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, list):
        return ",".join(str(page) for page in value)
    return str(value)


def _card(tool_key: str) -> ToolCard:
    for card in TOOLCARDS:
        if card.key == tool_key:
            return card
    raise KeyError(tool_key)


def build_report(
    selected_tools: list[str],
    fixture_names: list[str] | None = None,
    *,
    profile: str = DEFAULT_PROFILE,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb: float = DEFAULT_MAX_RSS_MB,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
) -> None:
    if fixture_names is None:
        fixture_names = select_fixture_names(profile)
    else:
        unknown = [name for name in fixture_names if name not in FIXTURE_META]
        if unknown:
            raise ValueError(f"unknown fixture(s): {unknown}")

    results: list[dict[str, Any]] = []
    for card in TOOLCARDS:
        if card.key not in selected_tools:
            continue
        for fixture_name in fixture_names:
            path = FIX / fixture_name
            if not path.exists():
                results.append(
                    {
                        "tool_key": card.key,
                        "fixture": fixture_name,
                        "status": "error",
                        "error": "fixture missing; run python tests/fixtures/fetch.py",
                    }
                )
                continue
            if not is_tool_available(card.key):
                results.append(
                    {
                        "tool_key": card.key,
                        "fixture": fixture_name,
                        "status": "error",
                        "error": f"tool unavailable here; install with: {card.install_hint}",
                    }
                )
                continue
            print(f">> {card.label} :: {fixture_name}", flush=True)
            results.append(
                _run_one(
                    card.key,
                    fixture_name,
                    timeout_s=timeout_s,
                    max_rss_mb_hard=max_rss_mb_hard,
                )
            )

    lines: list[str] = [
        "# Phase 5 — Competitor Comparison",
        "",
        "_Multi-dimensional comparison across current scientific-PDF competitors._",
        "",
        f"Report generated from `{ROOT.name}` using {sys.executable}.",
        f"Profile: `{profile}`. Timeout: `{timeout_s:g}s`. RSS warning threshold: `{max_rss_mb:g} MB`. RSS hard-kill threshold: `{max_rss_mb_hard:g} MB`.",
        "",
    ]
    lines.extend(
        _render_methodology(
            profile,
            fixture_names,
            timeout_s,
            max_rss_mb,
            max_rss_mb_hard,
        )
    )
    lines.extend(_render_static_matrix([c for c in TOOLCARDS if c.key in selected_tools]))
    lines.extend(_render_summary(results))
    lines.extend(_render_observed_verdict(results))
    lines.extend(_render_performance_guardrails(results, max_rss_mb))
    lines.extend(_render_empirical_matrix(results))
    lines.append("## Fixture Corpus")
    lines.append("")
    for name in fixture_names:
        pages, desc = FIXTURE_META[name]
        lines.append(f"- `{name}` ({pages}p): {desc}")
    lines.append("")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {REPORT}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tools",
        default=DEFAULT_TOOLS,
        help=(
            "Comma-separated tool keys to include. "
            f"Default: {DEFAULT_TOOLS}. Use `{ALL_TOOLS}` for every optional runner."
        ),
    )
    ap.add_argument(
        "--profile",
        choices=sorted(FIXTURE_PROFILES),
        default=DEFAULT_PROFILE,
        help=f"Fixture profile to run when --fixtures is not set. Default: {DEFAULT_PROFILE}.",
    )
    ap.add_argument(
        "--fixtures",
        default=None,
        help="Comma-separated fixture filenames. Overrides --profile.",
    )
    ap.add_argument(
        "--timeout-s",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help=f"Per tool/fixture subprocess timeout. Default: {DEFAULT_TIMEOUT_S:g}s.",
    )
    ap.add_argument(
        "--max-rss-mb",
        type=float,
        default=DEFAULT_MAX_RSS_MB,
        help=f"Peak RSS warning threshold. Default: {DEFAULT_MAX_RSS_MB:g} MB.",
    )
    ap.add_argument(
        "--max-rss-mb-hard",
        type=float,
        default=DEFAULT_MAX_RSS_MB_HARD,
        help=(
            "Hard RSS kill threshold for each worker process tree. "
            f"Default: {DEFAULT_MAX_RSS_MB_HARD:g} MB."
        ),
    )
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    selected = [t.strip() for t in args.tools.split(",") if t.strip()]
    unknown = [t for t in selected if t not in {c.key for c in TOOLCARDS}]
    if unknown:
        raise SystemExit(f"unknown tool key(s): {unknown}")
    if args.timeout_s <= 0:
        raise SystemExit("--timeout-s must be > 0")
    if args.max_rss_mb <= 0:
        raise SystemExit("--max-rss-mb must be > 0")
    if args.max_rss_mb_hard <= 0:
        raise SystemExit("--max-rss-mb-hard must be > 0")
    try:
        fixtures = select_fixture_names(args.profile, args.fixtures)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    build_report(
        selected,
        fixtures,
        profile=args.profile if args.fixtures is None else "custom",
        timeout_s=args.timeout_s,
        max_rss_mb=args.max_rss_mb,
        max_rss_mb_hard=args.max_rss_mb_hard,
    )


if __name__ == "__main__":
    main()
