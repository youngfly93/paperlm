"""Phase 8 long-PDF performance probe.

This is a targeted alternative to the full competitor matrix. It runs one
long fixture in isolated subprocesses and records where paperlm spends time:

- scanned text-layer probe
- Docling conversion
- IR post-processing
- Markdown rendering
- JSON sidecar serialization

Formula LaTeX enrichment is not run by default. Use --include-formula only
when you intentionally want to measure that opt-in heavy path.

Use --profile-cpu to include cProfile cumulative top-N output for each worker.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
ROOT = HERE.parent
FIX = ROOT / "tests" / "fixtures"
REPORT = HERE / "phase8_long_pdf_perf_report.md"
DEFAULT_FIXTURE = "sample_arxiv_math.pdf"
DEFAULT_TIMEOUT_S = 600.0
DEFAULT_MAX_RSS_MB_HARD = 6144.0
DEFAULT_PROFILE_TOP_N = 30
DEFAULT_TOOLS = ("docling_standalone", "paperlm_markitdown", "paperlm_breakdown")
TOOL_LABELS = {
    "docling_standalone": "Docling standalone",
    "paperlm_markitdown": "paperlm via MarkItDown",
    "paperlm_breakdown": "paperlm breakdown",
    "paperlm_formula": "paperlm breakdown + formula VLM",
}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.process_guard import run_guarded_subprocess  # noqa: E402

WORKER = r"""
from __future__ import annotations

import cProfile
import io
import json
import pstats
import re
import resource
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1])
SRC = ROOT / "src"
pdf_path = Path(sys.argv[2])
tool_key = sys.argv[3]
profile_cpu = sys.argv[4] == "1"
profile_top_n = int(sys.argv[5])

sys.path.insert(0, str(SRC))


def peak_rss_mb() -> float:
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 * 1024) if sys.platform == "darwin" else rss / 1024


def first_nonempty_line(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return ""


def summarize_markdown(markdown: str, meta: dict, timings: dict[str, float]) -> dict:
    return {
        "status": "ok" if markdown.strip() else "empty",
        "chars": len(markdown),
        "lines": len(markdown.splitlines()),
        "headings": sum(1 for line in markdown.splitlines() if re.match(r"^#{1,6}\s", line)),
        "tables": sum(1 for line in markdown.splitlines() if line.strip().startswith("|")),
        "formula_markers": markdown.count("$$"),
        "first_line": first_nonempty_line(markdown),
        "meta": meta,
        "timings": timings,
    }


def timed(timings: dict[str, float], name: str, fn):
    start = time.perf_counter()
    value = fn()
    timings[name] = round(time.perf_counter() - start, 3)
    return value


def run_docling_standalone(pdf_path: Path) -> dict:
    timings: dict[str, float] = {}
    from docling.document_converter import DocumentConverter

    converter = timed(timings, "docling_init", DocumentConverter)
    result = timed(timings, "docling_convert", lambda: converter.convert(str(pdf_path)))
    markdown = timed(timings, "docling_markdown_export", result.document.export_to_markdown)
    return summarize_markdown(markdown, {"engine_used": "docling"}, timings)


def run_paperlm_markitdown(pdf_path: Path, *, enable_formula: bool) -> dict:
    timings: dict[str, float] = {}
    from markitdown import MarkItDown
    from markitdown_paperlm import register_converters

    def build_converter():
        md = MarkItDown()
        register_converters(
            md,
            paperlm_engine="auto",
            paperlm_enable_ocr=False,
            paperlm_enable_formula=enable_formula,
        )
        return md

    md = timed(timings, "markitdown_init", build_converter)
    result = timed(timings, "markitdown_convert", lambda: md.convert(str(pdf_path)))
    ir = getattr(result, "ir", None)
    meta = {
        "engine_used": getattr(result, "engine_used", "unknown"),
        "blocks": len(getattr(ir, "blocks", []) or []),
        "warnings": getattr(ir, "warnings", []) if ir is not None else [],
        "formula_enabled": enable_formula,
    }
    return summarize_markdown(result.markdown, meta, timings)


def run_paperlm_breakdown(pdf_path: Path, *, enable_formula: bool) -> dict:
    timings: dict[str, float] = {}

    from docling.datamodel.base_models import DocumentStream

    from markitdown_paperlm.engines.docling_adapter import DoclingAdapter
    from markitdown_paperlm.serializers.json_sidecar import ir_to_chunks_jsonl, ir_to_dict
    from markitdown_paperlm.serializers.markdown import MarkdownSerializer
    from markitdown_paperlm.utils.scanned_detector import is_scanned_pdf

    data = pdf_path.read_bytes()
    scanned = timed(timings, "scanned_check", lambda: is_scanned_pdf(io.BytesIO(data)))
    adapter = DoclingAdapter(enable_formula=enable_formula)
    converter = timed(timings, "docling_init", adapter._get_converter)
    source = DocumentStream(name=pdf_path.name, stream=io.BytesIO(data))
    docling_result = timed(timings, "docling_convert", lambda: converter.convert(source))
    ir = timed(timings, "ir_postprocess", lambda: adapter._docling_to_ir(docling_result.document))
    markdown = timed(timings, "markdown_render", lambda: MarkdownSerializer().render(ir))
    timed(timings, "json_sidecars", lambda: (ir_to_dict(ir), ir_to_chunks_jsonl(ir)))
    meta = {
        "engine_used": ir.engine_used,
        "blocks": len(ir.blocks),
        "warnings": ir.warnings,
        "formula_enabled": enable_formula,
        "scanned": {
            "is_scanned": scanned.is_scanned,
            "reason": scanned.reason,
        },
    }
    return summarize_markdown(markdown, meta, timings)


RUNNERS = {
    "docling_standalone": lambda path: run_docling_standalone(path),
    "paperlm_markitdown": lambda path: run_paperlm_markitdown(path, enable_formula=False),
    "paperlm_breakdown": lambda path: run_paperlm_breakdown(path, enable_formula=False),
    "paperlm_formula": lambda path: run_paperlm_breakdown(path, enable_formula=True),
}

started = time.perf_counter()
result = {
    "tool_key": tool_key,
    "fixture": pdf_path.name,
}

try:
    profiler = cProfile.Profile() if profile_cpu else None
    if profiler is None:
        payload = RUNNERS[tool_key](pdf_path)
    else:
        payload = profiler.runcall(lambda: RUNNERS[tool_key](pdf_path))
    result.update(payload)
except Exception as exc:
    result.update(
        {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
    )
finally:
    if profile_cpu and "profiler" in locals() and profiler is not None:
        profile_out = io.StringIO()
        stats = pstats.Stats(profiler, stream=profile_out)
        stats.strip_dirs().sort_stats("cumulative").print_stats(profile_top_n)
        result["profile_cumulative"] = profile_out.getvalue()
    result["elapsed_s"] = round(time.perf_counter() - started, 2)
    result["peak_mem_mb"] = round(peak_rss_mb(), 1)

sys.stdout.write(json.dumps(result, ensure_ascii=True))
"""


def run_probe(
    *,
    fixture: str,
    tools: list[str],
    timeout_s: float = DEFAULT_TIMEOUT_S,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
    profile_cpu: bool = False,
    profile_top_n: int = DEFAULT_PROFILE_TOP_N,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for tool_key in tools:
        results.append(
            _run_one(
                tool_key,
                fixture,
                timeout_s=timeout_s,
                max_rss_mb_hard=max_rss_mb_hard,
                profile_cpu=profile_cpu,
                profile_top_n=profile_top_n,
            )
        )
    return results


def _run_one(
    tool_key: str,
    fixture: str,
    *,
    timeout_s: float,
    max_rss_mb_hard: float,
    profile_cpu: bool = False,
    profile_top_n: int = DEFAULT_PROFILE_TOP_N,
) -> dict[str, Any]:
    path = FIX / fixture
    if not path.exists():
        return {
            "tool_key": tool_key,
            "fixture": fixture,
            "status": "error",
            "error": "fixture missing; run python tests/fixtures/fetch.py",
        }

    proc = run_guarded_subprocess(
        [
            sys.executable,
            "-c",
            WORKER,
            str(ROOT),
            str(path),
            tool_key,
            "1" if profile_cpu else "0",
            str(profile_top_n),
        ],
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
    row = json.loads(proc.stdout)
    if proc.peak_rss_mb is not None:
        worker_peak = _to_float(row.get("peak_mem_mb"))
        row["peak_mem_mb"] = round(max(worker_peak or 0.0, proc.peak_rss_mb), 1)
    return row


def render_report(
    results: list[dict[str, Any]],
    *,
    timeout_s: float,
    max_rss_mb_hard: float = DEFAULT_MAX_RSS_MB_HARD,
    profile_cpu: bool = False,
    profile_top_n: int = DEFAULT_PROFILE_TOP_N,
) -> str:
    lines = [
        "# Phase 8 - Long PDF Performance Probe",
        "",
        "Targeted long-document profiling. Formula LaTeX enrichment is off by default.",
        "",
        f"Timeout per subprocess: `{timeout_s:g}s`; RSS hard-kill threshold: `{max_rss_mb_hard:g} MB`.",
        f"CPU profiling: `{'on' if profile_cpu else 'off'}`; profile rows: `{profile_top_n}`.",
        "",
        "## Summary",
        "",
        "| Tool | Status | Time (s) | Peak RSS (MB) | Chars | Blocks | `$$` | First line / error |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for row in results:
        label = TOOL_LABELS.get(str(row.get("tool_key")), str(row.get("tool_key")))
        status = str(row.get("status", "unknown")).upper()
        meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
        blocks = meta.get("blocks", "-") if isinstance(meta, dict) else "-"
        detail = row.get("first_line") if row.get("status") == "ok" else row.get("error", "")
        lines.append(
            f"| {label} | {status} | {row.get('elapsed_s', '-')} | "
            f"{row.get('peak_mem_mb', '-')} | {row.get('chars', '-')} | "
            f"{blocks} | {row.get('formula_markers', '-')} | `{_compact(str(detail))[:110]}` |"
        )

    lines.extend(["", "## PaperLM Breakdown", ""])
    breakdown_rows = [
        row
        for row in results
        if str(row.get("tool_key", "")).startswith("paperlm")
        and isinstance(row.get("timings"), dict)
    ]
    if not breakdown_rows:
        lines.extend(["No paperlm timing breakdown is available.", ""])
    else:
        for row in breakdown_rows:
            label = TOOL_LABELS.get(str(row["tool_key"]), str(row["tool_key"]))
            timings = row["timings"]
            total = sum(float(value) for value in timings.values())
            lines.extend(
                [
                    f"### {label}",
                    "",
                    "| Step | Time (s) | Share |",
                    "|---|---|---|",
                ]
            )
            for name, value in timings.items():
                seconds = float(value)
                share = seconds / total if total else 0.0
                lines.append(f"| `{name}` | {seconds:.3f} | {share:.1%} |")
            lines.append("")

    lines.extend(_render_cpu_profiles(results))
    lines.extend(_render_observations(results))
    return "\n".join(lines).rstrip() + "\n"


def _render_cpu_profiles(results: list[dict[str, Any]]) -> list[str]:
    rows = [row for row in results if row.get("profile_cumulative")]
    if not rows:
        return []

    lines = ["## CPU Profiles", ""]
    for row in rows:
        label = TOOL_LABELS.get(str(row.get("tool_key")), str(row.get("tool_key")))
        lines.extend(
            [
                f"### {label}",
                "",
                "```text",
                str(row["profile_cumulative"]).rstrip(),
                "```",
                "",
            ]
        )
    return lines


def _render_observations(results: list[dict[str, Any]]) -> list[str]:
    lines = ["## Observations", ""]
    by_tool = {row.get("tool_key"): row for row in results if row.get("status") == "ok"}
    docling = by_tool.get("docling_standalone")
    paperlm = by_tool.get("paperlm_markitdown") or by_tool.get("paperlm_breakdown")
    formula = by_tool.get("paperlm_formula")

    if docling and paperlm:
        docling_time = _to_float(docling.get("elapsed_s"))
        paperlm_time = _to_float(paperlm.get("elapsed_s"))
        if docling_time and paperlm_time:
            ratio = paperlm_time / docling_time
            lines.append(
                f"- `paperlm` was `{ratio:.2f}x` Docling standalone on this fixture "
                f"({paperlm_time:.2f}s vs {docling_time:.2f}s)."
            )

    if formula and paperlm:
        formula_time = _to_float(formula.get("elapsed_s"))
        paperlm_time = _to_float(paperlm.get("elapsed_s"))
        if formula_time and paperlm_time:
            ratio = formula_time / paperlm_time
            lines.append(
                f"- Opt-in formula enrichment was `{ratio:.2f}x` the default paperlm path "
                f"({formula_time:.2f}s vs {paperlm_time:.2f}s)."
            )

    if len(lines) == 2:
        lines.append("- Not enough successful rows to compare runtime ratios.")
    lines.append("")
    return lines


def _compact(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


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


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fixture", default=DEFAULT_FIXTURE)
    ap.add_argument(
        "--tools",
        default=",".join(DEFAULT_TOOLS),
        help="Comma-separated tool keys. Defaults to docling + paperlm non-formula probes.",
    )
    ap.add_argument(
        "--include-formula",
        action="store_true",
        help="Also run the opt-in formula-enrichment path. This may be much slower.",
    )
    ap.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--max-rss-mb-hard", type=float, default=DEFAULT_MAX_RSS_MB_HARD)
    ap.add_argument(
        "--profile-cpu",
        action="store_true",
        help="Include cProfile cumulative top-N output for each worker.",
    )
    ap.add_argument(
        "--profile-top-n",
        type=int,
        default=DEFAULT_PROFILE_TOP_N,
        help=f"Number of cumulative cProfile rows to print. Default: {DEFAULT_PROFILE_TOP_N}.",
    )
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    if args.timeout_s <= 0:
        raise SystemExit("--timeout-s must be > 0")
    if args.max_rss_mb_hard <= 0:
        raise SystemExit("--max-rss-mb-hard must be > 0")
    if args.profile_top_n <= 0:
        raise SystemExit("--profile-top-n must be > 0")

    tools = [tool.strip() for tool in args.tools.split(",") if tool.strip()]
    if args.include_formula and "paperlm_formula" not in tools:
        tools.append("paperlm_formula")
    unknown = [tool for tool in tools if tool not in TOOL_LABELS]
    if unknown:
        raise SystemExit(f"unknown tool key(s): {unknown}")

    results = run_probe(
        fixture=args.fixture,
        tools=tools,
        timeout_s=args.timeout_s,
        max_rss_mb_hard=args.max_rss_mb_hard,
        profile_cpu=args.profile_cpu,
        profile_top_n=args.profile_top_n,
    )
    report = render_report(
        results,
        timeout_s=args.timeout_s,
        max_rss_mb_hard=args.max_rss_mb_hard,
        profile_cpu=args.profile_cpu,
        profile_top_n=args.profile_top_n,
    )
    REPORT.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT}")


if __name__ == "__main__":
    main()
