"""Unified benchmark report for paperlm.

This is the release-facing benchmark entrypoint. It combines the two
signals we already care about:

* conversion/performance evidence from the competitor matrix
* curated text recall + reading-order evidence from the quality probe

Default runs intentionally stay conservative: paperlm, raw MarkItDown, and
Docling only. Marker/MinerU remain opt-in because they are heavy and can
exhaust memory on developer machines.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parent
SRC = ROOT / "src"
FIX = ROOT / "tests" / "fixtures"
REPORT_DIR = HERE / "reports"
DEFAULT_TIMEOUT_S = 240.0
DEFAULT_MAX_RSS_MB = 4096.0
DEFAULT_MAX_RSS_MB_HARD = 6144.0
DEFAULT_TOOLS = "paperlm_plugin,markitdown_baseline,docling_standalone"
SCHEMA_VERSION = 1

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks import phase5_competitor_compare as phase5  # noqa: E402
from benchmarks import phase6_quality_probe as phase6  # noqa: E402
from benchmarks.process_guard import run_guarded_subprocess  # noqa: E402


@dataclass(frozen=True)
class FixtureInfo:
    filename: str
    pages: int
    description: str


TOOLCARDS = {card.key: card for card in phase5.TOOLCARDS}
ALL_TOOL_KEYS = tuple(TOOLCARDS)
FIXTURE_META: dict[str, FixtureInfo] = {
    name: FixtureInfo(name, pages, desc)
    for name, (pages, desc) in phase5.FIXTURE_META.items()
}
FIXTURE_PROFILES: dict[str, tuple[str, ...]] = {
    "smoke": phase5.FIXTURE_PROFILES["smoke"],
    "quality": phase6.DEFAULT_FIXTURES,
    "full": tuple(FIXTURE_META),
}


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
            return stripped[:160]
    return ""


def run_markitdown_baseline(pdf_path: Path):
    from markitdown import MarkItDown

    result = MarkItDown().convert(str(pdf_path))
    return result.markdown, {"engine_used": "markitdown", "warnings": []}


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
    return result.markdown, {
        "engine_used": getattr(result, "engine_used", "unknown"),
        "warnings": getattr(ir, "warnings", []),
        "metadata": getattr(ir, "metadata", {}),
    }


def run_docling_standalone(pdf_path: Path):
    from docling.document_converter import DocumentConverter

    result = DocumentConverter().convert(str(pdf_path))
    return result.document.export_to_markdown(), {
        "engine_used": "docling",
        "warnings": [],
    }


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
        return _largest_markdown(out_dir), {"engine_used": "marker", "warnings": []}


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
        return _largest_markdown(out_dir), {"engine_used": "mineru", "warnings": []}


RUNNERS = {
    "markitdown_baseline": run_markitdown_baseline,
    "paperlm_plugin": run_paperlm_plugin,
    "docling_standalone": run_docling_standalone,
    "marker_cli": run_marker_cli,
    "mineru_cli": run_mineru_cli,
}

t0 = time.perf_counter()
result = {"tool_key": tool_key, "fixture": pdf_path.name}

try:
    markdown, meta = RUNNERS[tool_key](pdf_path)
    elapsed = time.perf_counter() - t0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mb = rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024
    warnings = meta.get("warnings", [])
    ocr_meta = (meta.get("metadata") or {}).get("ocr", {})
    status = "ok" if markdown.strip() else "empty"
    error = ""
    if status == "empty":
        error = " | ".join(str(w) for w in warnings[:2]) if warnings else "empty markdown"
    first_line = first_nonempty_line(markdown)
    result.update(
        {
            "status": status,
            "elapsed_s": round(elapsed, 2),
            "peak_rss_mb": round(peak_mb, 1),
            "chars": len(markdown),
            "lines": len(markdown.splitlines()),
            "headings": sum(1 for line in markdown.splitlines() if re.match(r"^#{1,6}\s", line)),
            "tables": count_tables(markdown),
            "formula_markers": markdown.count("$$"),
            "cid_tokens": markdown.count("(cid:"),
            "first_line": first_line,
            "first_line_title_like": first_line.startswith("#"),
            "engine_used": meta.get("engine_used", ""),
            "warnings": warnings,
            "ocr_mean_confidence": ocr_meta.get("mean_confidence"),
            "ocr_low_confidence_pages": ocr_meta.get("low_confidence_pages", []),
            "markdown": markdown,
            "error": error,
        }
    )
except Exception as exc:
    result.update(
        {
            "status": "error",
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "error": f"{type(exc).__name__}: {exc}",
        }
    )

sys.stdout.write(json.dumps(result, ensure_ascii=True))
"""


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


def parse_tools(tools: str) -> list[str]:
    selected = [tool.strip() for tool in tools.split(",") if tool.strip()]
    unknown = [tool for tool in selected if tool not in TOOLCARDS]
    if unknown:
        raise ValueError(f"unknown tool key(s): {unknown}")
    return selected


def is_tool_available(tool_key: str) -> bool:
    if tool_key == "markitdown_baseline":
        return _module_available("markitdown") and _module_available("pdfminer.high_level")
    return phase5.is_tool_available(tool_key)


def run_one(
    tool_key: str,
    fixture_name: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
) -> dict[str, Any]:
    proc = run_guarded_subprocess(
        [sys.executable, "-c", WORKER, str(ROOT), str(FIX / fixture_name), tool_key],
        timeout_s=timeout_s,
        max_rss_mb_hard=max_rss_mb_hard,
    )
    if proc.status in {"timeout", "memory_limit"}:
        return {
            "tool_key": tool_key,
            "fixture": fixture_name,
            "status": proc.status,
            "elapsed_s": proc.elapsed_s,
            "peak_rss_mb": proc.peak_rss_mb,
            "error": _guard_error(proc.error, proc.stderr),
        }
    if proc.returncode != 0 or not proc.stdout.strip():
        tail = " | ".join((proc.stderr or "").strip().splitlines()[-3:])
        return {
            "tool_key": tool_key,
            "fixture": fixture_name,
            "status": "error",
            "elapsed_s": proc.elapsed_s,
            "peak_rss_mb": proc.peak_rss_mb,
            "error": tail or f"worker exit={proc.returncode}",
        }
    row = json.loads(proc.stdout)
    if proc.peak_rss_mb is not None:
        worker_peak = _to_float(row.get("peak_rss_mb"))
        row["peak_rss_mb"] = round(max(worker_peak or 0.0, proc.peak_rss_mb), 1)
    return row


def evaluate_result(row: dict[str, Any]) -> dict[str, Any]:
    markdown = str(row.pop("markdown", "") or "")
    fixture = str(row["fixture"])
    snippets = [snippet for snippet in phase6.REFERENCES if snippet.fixture == fixture]
    snippet_results = [phase6.score_snippet(markdown, snippet) for snippet in snippets]
    exact_hits = sum(1 for item in snippet_results if item["exact"])
    avg_score = (
        statistics.mean(float(item["score"]) for item in snippet_results)
        if snippet_results
        else None
    )
    order = phase6.evaluate_order(fixture, phase6.ORDER_CASES, snippet_results)
    return {
        **row,
        "snippet_total": len(snippet_results),
        "snippet_exact_hits": exact_hits,
        "snippet_avg_score": round(avg_score, 3) if avg_score is not None else None,
        "snippet_results": snippet_results,
        "order": order,
    }


def build_report(
    selected_tools: list[str],
    fixture_names: list[str],
    *,
    profile: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb: float = DEFAULT_MAX_RSS_MB,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []

    for tool_key in selected_tools:
        for fixture_name in fixture_names:
            rows.append(
                _collect_one(
                    tool_key,
                    fixture_name,
                    timeout_s=timeout_s,
                    max_rss_mb_hard=max_rss_mb_hard,
                )
            )

    summary = summarize_results(rows, selected_tools)
    guardrails = collect_guardrails(rows, max_rss_mb=max_rss_mb)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "profile": profile,
        "tools": selected_tools,
        "fixtures": [_fixture_to_dict(name) for name in fixture_names],
        "run_controls": {
            "timeout_s": timeout_s,
            "max_rss_mb": max_rss_mb,
            "max_rss_mb_hard": max_rss_mb_hard,
        },
        "summary": summary,
        "guardrails": guardrails,
        "results": rows,
    }


def _collect_one(
    tool_key: str,
    fixture_name: str,
    *,
    timeout_s: float,
    max_rss_mb_hard: float,
) -> dict[str, Any]:
    path = FIX / fixture_name
    base = {"tool_key": tool_key, "fixture": fixture_name}
    if not path.exists():
        return {
            **base,
            "status": "error",
            "elapsed_s": 0.0,
            "error": "fixture missing; run python tests/fixtures/fetch.py",
            "snippet_total": 0,
            "snippet_exact_hits": 0,
            "snippet_avg_score": None,
            "snippet_results": [],
            "order": None,
        }
    if not is_tool_available(tool_key):
        return {
            **base,
            "status": "error",
            "elapsed_s": 0.0,
            "error": f"tool unavailable; install with: {TOOLCARDS[tool_key].install_hint}",
            "snippet_total": 0,
            "snippet_exact_hits": 0,
            "snippet_avg_score": None,
            "snippet_results": [],
            "order": None,
        }

    print(f">> {TOOLCARDS[tool_key].label} :: {fixture_name}", flush=True)
    row = run_one(
        tool_key,
        fixture_name,
        timeout_s=timeout_s,
        max_rss_mb_hard=max_rss_mb_hard,
    )
    if row.get("status") == "ok":
        return evaluate_result(row)
    return {
        **row,
        "snippet_total": 0,
        "snippet_exact_hits": 0,
        "snippet_avg_score": None,
        "snippet_results": [],
        "order": None,
    }


def summarize_results(rows: list[dict[str, Any]], selected_tools: list[str]) -> dict[str, Any]:
    by_tool = _group_by_tool(rows)
    tools: dict[str, dict[str, Any]] = {}
    for tool_key in selected_tools:
        tool_rows = by_tool.get(tool_key, [])
        ok_rows = [row for row in tool_rows if row.get("status") == "ok"]
        scored_rows = [
            row for row in ok_rows if int(row.get("snippet_total") or 0) > 0
        ]
        exact_hits = sum(int(row.get("snippet_exact_hits") or 0) for row in scored_rows)
        snippet_total = sum(int(row.get("snippet_total") or 0) for row in scored_rows)
        order_cases = [
            order
            for order in (row.get("order") for row in ok_rows)
            if isinstance(order, dict)
        ]
        order_pass = sum(1 for order in order_cases if order.get("status") == "pass")
        avg_scores = [
            float(row["snippet_avg_score"])
            for row in scored_rows
            if row.get("snippet_avg_score") is not None
        ]
        tools[tool_key] = {
            "label": TOOLCARDS[tool_key].label,
            "available": is_tool_available(tool_key),
            "successful_runs": len(ok_rows),
            "total_runs": len(tool_rows),
            "median_elapsed_s": _median(ok_rows, "elapsed_s"),
            "median_peak_rss_mb": _median(ok_rows, "peak_rss_mb"),
            "median_chars": _median(ok_rows, "chars"),
            "snippet_exact_hits": exact_hits,
            "snippet_total": snippet_total,
            "snippet_avg_score": round(statistics.mean(avg_scores), 3)
            if avg_scores
            else None,
            "order_pass": order_pass,
            "order_total": len(order_cases),
        }
    return {
        "tools": tools,
        "executive_summary": executive_summary(tools),
    }


def executive_summary(tool_summary: dict[str, dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    paperlm = tool_summary.get("paperlm_plugin")
    baseline = tool_summary.get("markitdown_baseline")
    docling = tool_summary.get("docling_standalone")

    if paperlm and baseline:
        lines.append(
            f"paperlm succeeded on {paperlm['successful_runs']}/{paperlm['total_runs']} "
            f"runs vs MarkItDown baseline {baseline['successful_runs']}/{baseline['total_runs']}."
        )
        if paperlm["snippet_total"] or baseline["snippet_total"]:
            lines.append(
                f"On curated snippets, paperlm hit "
                f"{paperlm['snippet_exact_hits']}/{paperlm['snippet_total']} exactly vs "
                f"baseline {baseline['snippet_exact_hits']}/{baseline['snippet_total']}."
            )
    if paperlm and docling:
        lines.append(
            f"Against Docling, paperlm order checks were "
            f"{paperlm['order_pass']}/{paperlm['order_total']} vs "
            f"{docling['order_pass']}/{docling['order_total']}."
        )
        p_time = paperlm.get("median_elapsed_s")
        d_time = docling.get("median_elapsed_s")
        if p_time is not None and d_time is not None:
            lines.append(f"Median latency was paperlm {p_time:.2f}s vs Docling {d_time:.2f}s.")
    if not lines:
        lines.append("Not enough successful rows to produce a comparative summary.")
    return lines


def collect_guardrails(rows: list[dict[str, Any]], *, max_rss_mb: float) -> list[dict[str, Any]]:
    guardrails: list[dict[str, Any]] = []
    ok_by_tool_fixture = {
        (row["tool_key"], row["fixture"]): row for row in rows if row.get("status") == "ok"
    }

    for row in rows:
        status = row.get("status")
        if status in {"timeout", "memory_limit", "empty", "error"}:
            guardrails.append(
                {
                    "tool_key": row["tool_key"],
                    "fixture": row["fixture"],
                    "kind": str(status),
                    "detail": str(row.get("error", "")),
                }
            )
        peak = _to_float(row.get("peak_rss_mb"))
        if peak is not None and peak > max_rss_mb:
            guardrails.append(
                {
                    "tool_key": row["tool_key"],
                    "fixture": row["fixture"],
                    "kind": "rss",
                    "detail": (
                        f"peak RSS {peak:.1f} MB exceeded warning threshold "
                        f"{max_rss_mb:g} MB"
                    ),
                }
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
                {
                    "tool_key": "paperlm_plugin",
                    "fixture": fixture,
                    "kind": "latency",
                    "detail": (
                        f"{paperlm_time:.2f}s was >3x Docling standalone "
                        f"({docling_time:.2f}s)"
                    ),
                }
            )
    return guardrails


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# paperlm Benchmark Report",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Profile: `{report['profile']}`",
        (
            "Tools: "
            + ", ".join(f"`{tool}`" for tool in report["tools"])
        ),
        "",
        "## Executive Summary",
        "",
    ]
    for item in report["summary"]["executive_summary"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.extend(_render_corpus(report))
    lines.extend(_render_tool_summary(report))
    lines.extend(_render_quality_matrix(report))
    lines.extend(_render_performance_matrix(report))
    lines.extend(_render_guardrails(report))
    lines.extend(_render_interpretation())
    return "\n".join(lines) + "\n"


def _render_corpus(report: dict[str, Any]) -> list[str]:
    lines = ["## Corpus", ""]
    for fixture in report["fixtures"]:
        lines.append(
            f"- `{fixture['filename']}` ({fixture['pages']}p): {fixture['description']}"
        )
    lines.append("")
    return lines


def _render_tool_summary(report: dict[str, Any]) -> list[str]:
    lines = [
        "## Tool Summary",
        "",
        "| Tool | Available | Success | Median time (s) | Median RSS (MB) | Exact snippets | Avg score | Order pass |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for tool_key in report["tools"]:
        row = report["summary"]["tools"][tool_key]
        lines.append(
            f"| {row['label']} | {'yes' if row['available'] else 'no'} | "
            f"{row['successful_runs']}/{row['total_runs']} | "
            f"{_fmt(row['median_elapsed_s'])} | {_fmt(row['median_peak_rss_mb'])} | "
            f"{row['snippet_exact_hits']}/{row['snippet_total']} | "
            f"{_fmt(row['snippet_avg_score'])} | "
            f"{row['order_pass']}/{row['order_total']} |"
        )
    lines.append("")
    return lines


def _render_quality_matrix(report: dict[str, Any]) -> list[str]:
    lines = [
        "## Quality Matrix",
        "",
        "| Tool | Fixture | Status | Engine | First line title-like | Exact snippets | Avg score | Order | First line / error |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["results"]:
        label = TOOLCARDS[row["tool_key"]].label
        if row["status"] != "ok":
            lines.append(
                f"| {label} | `{row['fixture']}` | {str(row['status']).upper()} | — | — | — | — | — | "
                f"`{_esc(str(row.get('error', '')))[:140]}` |"
            )
            continue
        order = row.get("order")
        order_status = "—"
        if isinstance(order, dict):
            order_status = str(order.get("status", "—"))
            if order_status == "missing":
                order_status += " " + ",".join(str(x) for x in order.get("missing", []))
        lines.append(
            f"| {label} | `{row['fixture']}` | OK | {row.get('engine_used', '—')} | "
            f"{'yes' if row.get('first_line_title_like') else 'no'} | "
            f"{row.get('snippet_exact_hits', 0)}/{row.get('snippet_total', 0)} | "
            f"{_fmt(row.get('snippet_avg_score'))} | {order_status} | "
            f"`{_esc(str(row.get('first_line', '')))}` |"
        )
    lines.append("")
    return lines


def _render_performance_matrix(report: dict[str, Any]) -> list[str]:
    lines = [
        "## Performance Matrix",
        "",
        "| Tool | Fixture | Status | Time (s) | Peak RSS (MB) | Chars | Lines | Headings | Tables | `$$` | `(cid:)` | OCR mean | OCR low pages |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in report["results"]:
        label = TOOLCARDS[row["tool_key"]].label
        lines.append(
            f"| {label} | `{row['fixture']}` | {str(row.get('status', '—')).upper()} | "
            f"{_fmt(row.get('elapsed_s'))} | {_fmt(row.get('peak_rss_mb'))} | "
            f"{row.get('chars', '—')} | {row.get('lines', '—')} | "
            f"{row.get('headings', '—')} | {row.get('tables', '—')} | "
            f"{row.get('formula_markers', '—')} | {row.get('cid_tokens', '—')} | "
            f"{_fmt(row.get('ocr_mean_confidence'))} | "
            f"{_fmt_pages(row.get('ocr_low_confidence_pages'))} |"
        )
    lines.append("")
    return lines


def _render_guardrails(report: dict[str, Any]) -> list[str]:
    lines = ["## Failure / Guardrails", ""]
    guardrails = report["guardrails"]
    if not guardrails:
        lines.append("No timeout, memory-limit, empty-output, or latency guardrails fired.")
        lines.append("")
        return lines
    lines.extend(["| Tool | Fixture | Guardrail | Detail |", "|---|---|---|---|"])
    for row in guardrails:
        lines.append(
            f"| {TOOLCARDS[row['tool_key']].label} | `{row['fixture']}` | "
            f"{row['kind']} | {_esc(row['detail'])} |"
        )
    lines.append("")
    return lines


def _render_interpretation() -> list[str]:
    return [
        "## Interpretation",
        "",
        "- This report is corpus-specific evidence, not a universal accuracy claim.",
        "- Snippet recall checks curated anchors, not complete full-document ground truth.",
        "- Reading-order pass requires exact anchor matches; partial matches are marked missing.",
        "- Marker and MinerU are intentionally opt-in because their installs and model stacks are heavy.",
        "",
    ]


def write_outputs(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "latest.md"
    json_path = output_dir / "latest.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return md_path, json_path


def _fixture_to_dict(name: str) -> dict[str, Any]:
    fixture = FIXTURE_META[name]
    return {
        "filename": fixture.filename,
        "pages": fixture.pages,
        "description": fixture.description,
    }


def _group_by_tool(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["tool_key"], []).append(row)
    return grouped


def _median(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [_to_float(row.get(key)) for row in rows]
    numeric = [value for value in values if value is not None]
    if not numeric:
        return None
    return round(statistics.median(numeric), 3)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _fmt_pages(value: Any) -> str:
    if not value:
        return "—"
    if isinstance(value, list):
        return ",".join(str(page) for page in value)
    return str(value)


def _esc(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


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


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tools",
        default=DEFAULT_TOOLS,
        help=(
            "Comma-separated tool keys. "
            f"Default: {DEFAULT_TOOLS}. Available: {','.join(ALL_TOOL_KEYS)}"
        ),
    )
    ap.add_argument(
        "--profile",
        choices=sorted(FIXTURE_PROFILES),
        default="full",
        help="Fixture profile to run when --fixtures is not set. Default: full.",
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
    ap.add_argument(
        "--output-dir",
        default=str(REPORT_DIR),
        help="Directory for latest.md and latest.json. Default: benchmarks/reports.",
    )
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    try:
        selected_tools = parse_tools(args.tools)
        fixtures = select_fixture_names(args.profile, args.fixtures)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if args.timeout_s <= 0:
        raise SystemExit("--timeout-s must be > 0")
    if args.max_rss_mb <= 0:
        raise SystemExit("--max-rss-mb must be > 0")
    if args.max_rss_mb_hard <= 0:
        raise SystemExit("--max-rss-mb-hard must be > 0")

    profile = args.profile if args.fixtures is None else "custom"
    report = build_report(
        selected_tools,
        fixtures,
        profile=profile,
        timeout_s=args.timeout_s,
        max_rss_mb=args.max_rss_mb,
        max_rss_mb_hard=args.max_rss_mb_hard,
    )
    md_path, json_path = write_outputs(report, Path(args.output_dir))
    print(f"\nWrote {md_path}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
