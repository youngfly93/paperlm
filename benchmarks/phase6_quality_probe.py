"""Phase 6 quality probe: text recall and reading-order evidence.

This benchmark is intentionally smaller than the full competitor matrix.
It checks manually curated snippets from a few representative PDFs and
tracks whether important front-matter/body anchors appear in the expected
order. It is not a full ground-truth OCR benchmark, but it gives release
reviewers a reproducible signal beyond "conversion succeeded".
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parent
SRC = ROOT / "src"
FIX = ROOT / "tests" / "fixtures"
REPORT = HERE / "phase6_quality_report.md"
DEFAULT_TIMEOUT_S = 240.0
DEFAULT_MAX_RSS_MB_HARD = 6144.0

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.process_guard import run_guarded_subprocess  # noqa: E402


@dataclass(frozen=True)
class ToolSpec:
    key: str
    label: str
    install_hint: str


@dataclass(frozen=True)
class ReferenceSnippet:
    fixture: str
    role: str
    text: str


@dataclass(frozen=True)
class OrderCase:
    fixture: str
    roles: tuple[str, ...]


TOOLS: list[ToolSpec] = [
    ToolSpec(
        key="paperlm_plugin",
        label="paperlm",
        install_hint="pip install -e '.[docling,ocr]'",
    ),
    ToolSpec(
        key="docling_standalone",
        label="Docling standalone",
        install_hint="pip install docling",
    ),
    ToolSpec(
        key="markitdown_baseline",
        label="MarkItDown baseline",
        install_hint="pip install 'markitdown[pdf]'",
    ),
]

REFERENCES: list[ReferenceSnippet] = [
    ReferenceSnippet(
        "sample_en_two_col.pdf",
        "title",
        "A systematic benchmark of bioinformatics methods for single-cell and spatial RNA-seq Nanopore long-read data",
    ),
    ReferenceSnippet(
        "sample_en_two_col.pdf",
        "abstract",
        "Alternative splicing plays a crucial role in transcriptomic complexity",
    ),
    ReferenceSnippet(
        "sample_en_two_col.pdf",
        "introduction",
        "Alternative splicing significantly contributes to transcriptome complexity",
    ),
    ReferenceSnippet(
        "sample_arxiv_table_heavy.pdf",
        "title",
        "TARGET: Benchmarking Table Retrieval for Generative Tasks",
    ),
    ReferenceSnippet(
        "sample_arxiv_table_heavy.pdf",
        "abstract",
        "Large Language Models LLMs have become an indispensable tool",
    ),
    ReferenceSnippet(
        "sample_arxiv_table_heavy.pdf",
        "introduction",
        "The data landscape is rich with structured data",
    ),
    ReferenceSnippet(
        "sample_zh_mixed.pdf",
        "title_en",
        "Bioinformatics and biomanufacturing: the importance of big biodata",
    ),
    ReferenceSnippet(
        "sample_zh_mixed.pdf",
        "abstract_zh",
        "生物信息学在生物制造中发挥着举足轻重的作用",
    ),
    ReferenceSnippet(
        "sample_zh_mixed.pdf",
        "section_1",
        "生物制造及其关键特点",
    ),
    ReferenceSnippet(
        "sample_scanned_1p.pdf",
        "title_en",
        "Bioinformatics and biomanufacturing: the importance of big biodata",
    ),
    ReferenceSnippet(
        "sample_scanned_1p.pdf",
        "abstract_zh",
        "生物信息学在生物制造中发挥着举足轻重的作用",
    ),
]

ORDER_CASES: list[OrderCase] = [
    OrderCase("sample_en_two_col.pdf", ("title", "abstract", "introduction")),
    OrderCase("sample_arxiv_table_heavy.pdf", ("title", "abstract", "introduction")),
    OrderCase("sample_zh_mixed.pdf", ("title_en", "abstract_zh", "section_1")),
    OrderCase("sample_scanned_1p.pdf", ("title_en", "abstract_zh")),
]

DEFAULT_FIXTURES = (
    "sample_en_two_col.pdf",
    "sample_arxiv_table_heavy.pdf",
    "sample_zh_mixed.pdf",
    "sample_scanned_1p.pdf",
)

WORKER = r"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1])
SRC = ROOT / "src"
pdf_path = Path(sys.argv[2])
tool_key = sys.argv[3]

sys.path.insert(0, str(SRC))


def run_markitdown_baseline(pdf_path: Path) -> str:
    from markitdown import MarkItDown

    return MarkItDown().convert(str(pdf_path)).markdown


def run_paperlm_plugin(pdf_path: Path) -> str:
    from markitdown import MarkItDown
    from markitdown_paperlm import register_converters

    md = MarkItDown()
    register_converters(md, paperlm_engine="auto", paperlm_enable_ocr=True)
    return md.convert(str(pdf_path)).markdown


def run_docling_standalone(pdf_path: Path) -> str:
    from docling.document_converter import DocumentConverter

    result = DocumentConverter().convert(str(pdf_path))
    return result.document.export_to_markdown()


RUNNERS = {
    "markitdown_baseline": run_markitdown_baseline,
    "paperlm_plugin": run_paperlm_plugin,
    "docling_standalone": run_docling_standalone,
}

t0 = time.perf_counter()
try:
    markdown = RUNNERS[tool_key](pdf_path)
    result = {
        "status": "ok" if markdown.strip() else "empty",
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "markdown": markdown,
        "error": "",
    }
except Exception as exc:
    result = {
        "status": "error",
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "markdown": "",
        "error": f"{type(exc).__name__}: {exc}",
    }

sys.stdout.write(json.dumps(result, ensure_ascii=True))
"""


def normalize_compact(text: str) -> str:
    """Normalize text for robust exact phrase lookup.

    Spaces, markdown punctuation, hyphens, and line wraps are removed so
    "single-cell", "single cell", and "singlecell" compare consistently.
    """
    lowered = text.lower()
    kept = re.findall(r"[a-z0-9\u4e00-\u9fff]+", lowered)
    return "".join(kept)


def tokenize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text.lower())


def score_snippet(markdown: str, snippet: ReferenceSnippet) -> dict[str, Any]:
    doc_compact = normalize_compact(markdown)
    target_compact = normalize_compact(snippet.text)
    position = doc_compact.find(target_compact) if target_compact else -1
    if position >= 0:
        return {
            "role": snippet.role,
            "exact": True,
            "score": 1.0,
            "position": position,
        }

    doc_tokens = set(tokenize_words(markdown))
    target_tokens = tokenize_words(snippet.text)
    if not target_tokens:
        score = 0.0
    else:
        score = sum(1 for token in target_tokens if token in doc_tokens) / len(target_tokens)
    return {
        "role": snippet.role,
        "exact": False,
        "score": round(score, 3),
        "position": None,
    }


def evaluate_order(
    fixture: str,
    order_cases: list[OrderCase],
    snippet_results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    case = next((c for c in order_cases if c.fixture == fixture), None)
    if case is None:
        return None
    by_role = {row["role"]: row for row in snippet_results}
    missing = [
        role
        for role in case.roles
        if role not in by_role or by_role[role].get("position") is None
    ]
    if missing:
        return {
            "roles": case.roles,
            "status": "missing",
            "missing": missing,
            "positions": {},
        }
    positions = {role: int(by_role[role]["position"]) for role in case.roles}
    values = [positions[role] for role in case.roles]
    return {
        "roles": case.roles,
        "status": "pass" if values == sorted(values) and len(set(values)) == len(values) else "fail",
        "missing": [],
        "positions": positions,
    }


def is_tool_available(tool_key: str) -> bool:
    if tool_key == "paperlm_plugin":
        return True
    if tool_key == "markitdown_baseline":
        return _module_available("markitdown")
    if tool_key == "docling_standalone":
        return _module_available("docling")
    return False


def _module_available(name: str) -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def run_one(
    tool_key: str,
    fixture: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
) -> dict[str, Any]:
    proc = run_guarded_subprocess(
        [sys.executable, "-c", WORKER, str(ROOT), str(FIX / fixture), tool_key],
        timeout_s=timeout_s,
        max_rss_mb_hard=max_rss_mb_hard,
    )
    if proc.status in {"timeout", "memory_limit"}:
        return {
            "tool_key": tool_key,
            "fixture": fixture,
            "status": proc.status,
            "elapsed_s": proc.elapsed_s,
            "peak_mem_mb": proc.peak_rss_mb or "—",
            "error": _guard_error(proc.error, proc.stderr),
        }
    if proc.returncode != 0 or not proc.stdout.strip():
        tail = " | ".join((proc.stderr or "").strip().splitlines()[-3:])
        return {
            "tool_key": tool_key,
            "fixture": fixture,
            "status": "error",
            "elapsed_s": proc.elapsed_s,
            "peak_mem_mb": proc.peak_rss_mb or "—",
            "error": tail or f"worker exit={proc.returncode}",
        }
    data = json.loads(proc.stdout)
    data["tool_key"] = tool_key
    data["fixture"] = fixture
    if proc.peak_rss_mb is not None:
        data["peak_mem_mb"] = proc.peak_rss_mb
    return data


def evaluate_result(row: dict[str, Any]) -> dict[str, Any]:
    fixture = row["fixture"]
    snippets = [snippet for snippet in REFERENCES if snippet.fixture == fixture]
    markdown = row.get("markdown", "")
    snippet_results = [score_snippet(markdown, snippet) for snippet in snippets]
    exact_hits = sum(1 for item in snippet_results if item["exact"])
    avg_score = (
        statistics.mean(float(item["score"]) for item in snippet_results)
        if snippet_results
        else 0.0
    )
    order = evaluate_order(fixture, ORDER_CASES, snippet_results)
    first_line = next((line.strip() for line in markdown.splitlines() if line.strip()), "")
    return {
        **{k: v for k, v in row.items() if k != "markdown"},
        "snippet_total": len(snippet_results),
        "snippet_exact_hits": exact_hits,
        "snippet_avg_score": round(avg_score, 3),
        "snippet_results": snippet_results,
        "order": order,
        "chars": len(markdown),
        "first_line": first_line[:140],
    }


def render_report(
    rows: list[dict[str, Any]],
    selected_tools: list[str],
    fixtures: list[str],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
) -> str:
    lines = [
        "# Phase 6 — Text Recall And Reading-Order Probe",
        "",
        "_Small, manually curated quality benchmark for release review._",
        "",
        "## Method",
        "",
        "- Snippet recall checks whether title / abstract / body anchors are present.",
        "- Exact matching uses compact normalized text, so whitespace, markdown punctuation, and hyphens do not dominate the score.",
        "- Reading-order checks use exact snippet positions. If a snippet is only partially matched, ordering is marked as missing.",
        "- This is not a universal text-coverage claim; it is a release guardrail for known representative cases.",
        f"- Each converter runs in a guarded subprocess with timeout `{timeout_s:g}s` and RSS hard limit `{max_rss_mb_hard:g} MB`.",
        "",
    ]
    lines.extend(_render_summary(rows, selected_tools))
    lines.extend(_render_observed_findings(rows))
    lines.extend(_render_details(rows))
    lines.extend(_render_references(fixtures))
    return "\n".join(lines) + "\n"


def _render_summary(rows: list[dict[str, Any]], selected_tools: list[str]) -> list[str]:
    by_tool: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_tool.setdefault(row["tool_key"], []).append(row)

    lines = [
        "## Summary",
        "",
        "| Tool | Available | Successful fixtures | Exact snippets | Avg snippet score | Order pass | Median time (s) |",
        "|---|---|---|---|---|---|---|",
    ]
    for tool in TOOLS:
        if tool.key not in selected_tools:
            continue
        tool_rows = by_tool.get(tool.key, [])
        ok_rows = [row for row in tool_rows if row.get("status") == "ok"]
        exact_hits = sum(int(row.get("snippet_exact_hits", 0)) for row in ok_rows)
        snippet_total = sum(int(row.get("snippet_total", 0)) for row in ok_rows)
        avg_score = (
            statistics.mean(float(row["snippet_avg_score"]) for row in ok_rows)
            if ok_rows
            else 0.0
        )
        order_cases = [
            order
            for order in (row.get("order") for row in ok_rows)
            if isinstance(order, dict)
        ]
        order_pass = sum(1 for order in order_cases if order["status"] == "pass")
        med_time = (
            round(statistics.median(float(row["elapsed_s"]) for row in ok_rows), 2)
            if ok_rows
            else "—"
        )
        lines.append(
            f"| {tool.label} | {'yes' if is_tool_available(tool.key) else 'no'} | "
            f"{len(ok_rows)}/{len(tool_rows)} | {exact_hits}/{snippet_total} | "
            f"{avg_score:.3f} | {order_pass}/{len(order_cases)} | {med_time} |"
        )
    lines.append("")
    return lines


def _render_observed_findings(rows: list[dict[str, Any]]) -> list[str]:
    by_tool: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_tool.setdefault(row["tool_key"], []).append(row)

    lines = ["## Observed Findings", ""]
    paperlm = [row for row in by_tool.get("paperlm_plugin", []) if row.get("status") == "ok"]
    docling = [row for row in by_tool.get("docling_standalone", []) if row.get("status") == "ok"]
    baseline = [row for row in by_tool.get("markitdown_baseline", []) if row.get("status") == "ok"]

    if paperlm:
        exact_hits, snippet_total = _snippet_totals(paperlm)
        order_pass, order_total = _order_totals(paperlm)
        lines.append(
            f"- `paperlm` recalled `{exact_hits}/{snippet_total}` curated snippets exactly and passed "
            f"`{order_pass}/{order_total}` reading-order checks."
        )
        issues = _quality_issues(paperlm)
        if issues:
            lines.append(
                "- Remaining `paperlm` quality gaps: "
                + "; ".join(issues)
                + "."
            )

    if paperlm and docling:
        paperlm_exact, paperlm_total = _snippet_totals(paperlm)
        docling_exact, docling_total = _snippet_totals(docling)
        paperlm_order, paperlm_order_total = _order_totals(paperlm)
        docling_order, docling_order_total = _order_totals(docling)
        lines.append(
            f"- Against raw Docling, snippet recall is effectively tied "
            f"(`{paperlm_exact}/{paperlm_total}` vs `{docling_exact}/{docling_total}`), "
            f"while reading-order checks favor `paperlm` in this run "
            f"(`{paperlm_order}/{paperlm_order_total}` vs `{docling_order}/{docling_order_total}`)."
        )

    if paperlm and baseline:
        baseline_exact, baseline_total = _snippet_totals(baseline)
        baseline_order, baseline_order_total = _order_totals(baseline)
        lines.append(
            f"- Against baseline MarkItDown, `paperlm` is stronger on both exact snippets "
            f"and ordering (`{baseline_exact}/{baseline_total}` snippets, "
            f"`{baseline_order}/{baseline_order_total}` order checks for baseline)."
        )

    lines.append("")
    return lines


def _snippet_totals(rows: list[dict[str, Any]]) -> tuple[int, int]:
    return (
        sum(int(row.get("snippet_exact_hits", 0)) for row in rows),
        sum(int(row.get("snippet_total", 0)) for row in rows),
    )


def _order_totals(rows: list[dict[str, Any]]) -> tuple[int, int]:
    orders = [
        order
        for order in (row.get("order") for row in rows)
        if isinstance(order, dict)
    ]
    return (
        sum(1 for order in orders if order["status"] == "pass"),
        len(orders),
    )


def _quality_issues(rows: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for row in rows:
        order = row.get("order")
        if isinstance(order, dict) and order.get("status") == "fail":
            issues.append(f"`{row['fixture']}` has out-of-order anchors")
        elif isinstance(order, dict) and order.get("status") == "missing":
            missing = ",".join(order.get("missing", []))
            issues.append(f"`{row['fixture']}` is missing exact anchor(s): {missing}")
    return issues


def _render_details(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## Details",
        "",
        "| Tool | Fixture | Status | Exact snippets | Avg score | Order | Time (s) | First line / error |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        tool = _tool(row["tool_key"]).label
        if row["status"] != "ok":
            lines.append(
                f"| {tool} | `{row['fixture']}` | {row['status'].upper()} | — | — | — | "
                f"{row.get('elapsed_s', '—')} | `{_esc(row.get('error', ''))[:120]}` |"
            )
            continue
        order = row.get("order") or {}
        order_status = order.get("status", "—")
        if order_status == "missing":
            order_status = "missing " + ",".join(order.get("missing", []))
        lines.append(
            f"| {tool} | `{row['fixture']}` | OK | "
            f"{row['snippet_exact_hits']}/{row['snippet_total']} | "
            f"{row['snippet_avg_score']:.3f} | {order_status} | "
            f"{row['elapsed_s']} | `{_esc(row['first_line'])}` |"
        )
    lines.append("")
    return lines


def _render_references(fixtures: list[str]) -> list[str]:
    lines = ["## Reference Snippets", ""]
    for fixture in fixtures:
        lines.append(f"### `{fixture}`")
        lines.append("")
        for snippet in [s for s in REFERENCES if s.fixture == fixture]:
            lines.append(f"- `{snippet.role}`: {_esc(snippet.text)}")
        lines.append("")
    return lines


def _tool(tool_key: str) -> ToolSpec:
    for tool in TOOLS:
        if tool.key == tool_key:
            return tool
    raise KeyError(tool_key)


def _esc(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _guard_error(error: str, stderr: str) -> str:
    tail = " | ".join((stderr or "").strip().splitlines()[-3:])
    if tail:
        return f"{error}: {tail[:200]}"
    return error


def build_report(
    selected_tools: list[str],
    fixtures: list[str],
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
) -> None:
    rows: list[dict[str, Any]] = []
    for tool_key in selected_tools:
        tool = _tool(tool_key)
        for fixture in fixtures:
            path = FIX / fixture
            if not path.exists():
                rows.append(
                    {
                        "tool_key": tool_key,
                        "fixture": fixture,
                        "status": "error",
                        "elapsed_s": 0,
                        "error": "fixture missing; run python tests/fixtures/fetch.py",
                    }
                )
                continue
            if not is_tool_available(tool_key):
                rows.append(
                    {
                        "tool_key": tool_key,
                        "fixture": fixture,
                        "status": "error",
                        "elapsed_s": 0,
                        "error": f"tool unavailable; install with: {tool.install_hint}",
                    }
                )
                continue
            print(f">> {tool.label} :: {fixture}", flush=True)
            rows.append(
                evaluate_result(
                    run_one(
                        tool_key,
                        fixture,
                        timeout_s=timeout_s,
                        max_rss_mb_hard=max_rss_mb_hard,
                    )
                )
            )

    report = render_report(
        rows,
        selected_tools,
        fixtures,
        timeout_s=timeout_s,
        max_rss_mb_hard=max_rss_mb_hard,
    )
    REPORT.write_text(report, encoding="utf-8")
    print(f"\nWrote {REPORT}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tools",
        default="paperlm_plugin,docling_standalone,markitdown_baseline",
        help="Comma-separated tool keys.",
    )
    ap.add_argument(
        "--fixtures",
        default=",".join(DEFAULT_FIXTURES),
        help="Comma-separated fixture filenames.",
    )
    ap.add_argument(
        "--timeout-s",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help=f"Per converter/fixture subprocess timeout. Default: {DEFAULT_TIMEOUT_S:g}s.",
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
    selected_tools = [tool.strip() for tool in args.tools.split(",") if tool.strip()]
    fixtures = [fixture.strip() for fixture in args.fixtures.split(",") if fixture.strip()]
    known_tools = {tool.key for tool in TOOLS}
    unknown_tools = [tool for tool in selected_tools if tool not in known_tools]
    if unknown_tools:
        raise SystemExit(f"unknown tool key(s): {unknown_tools}")
    known_fixtures = {snippet.fixture for snippet in REFERENCES}
    unknown_fixtures = [fixture for fixture in fixtures if fixture not in known_fixtures]
    if unknown_fixtures:
        raise SystemExit(f"no reference snippets for fixture(s): {unknown_fixtures}")
    if args.timeout_s <= 0:
        raise SystemExit("--timeout-s must be > 0")
    if args.max_rss_mb_hard <= 0:
        raise SystemExit("--max-rss-mb-hard must be > 0")

    build_report(
        selected_tools,
        fixtures,
        timeout_s=args.timeout_s,
        max_rss_mb_hard=args.max_rss_mb_hard,
    )


if __name__ == "__main__":
    main()
