"""Batch CLI for paperlm PDF ingestion."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from markitdown_paperlm.workers import DoclingWorkerPool, WorkerPoolResult


@dataclass(frozen=True)
class BatchItem:
    pdf_path: str
    item_id: str | None = None


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    items = _load_items(args)
    if not items:
        parser.error("provide at least one PDF path or --input-jsonl")

    output_stream = _open_output_jsonl(args.output_jsonl)
    close_output = output_stream is not sys.stdout
    started = time.perf_counter()
    try:
        counts = run_batch(items, args=args, output_stream=output_stream)
    finally:
        if close_output:
            output_stream.close()

    if args.summary:
        counts["wall_elapsed_s"] = round(time.perf_counter() - started, 3)
        sys.stderr.write(json.dumps(counts, ensure_ascii=False) + "\n")

    if counts["failed"] and not args.allow_failures:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperlm-batch",
        description="Batch-convert PDFs with reusable paperlm worker subprocesses.",
    )
    parser.add_argument("pdf_paths", nargs="*", help="PDF paths to convert.")
    parser.add_argument(
        "--input-jsonl",
        help="Optional JSONL input. Each line may be a string path or an object with pdf_path/path and optional id.",
    )
    parser.add_argument(
        "--output-jsonl",
        default="-",
        help="Where to write result JSONL. Use '-' for stdout. Default: stdout.",
    )
    parser.add_argument(
        "--output-dir",
        help="Optional directory for Markdown and sidecar artifacts.",
    )
    parser.add_argument(
        "--include-markdown",
        action="store_true",
        help="Include full Markdown in each output JSONL row. Off by default to keep JSONL small.",
    )
    parser.add_argument(
        "--no-sidecars",
        action="store_true",
        help="When --output-dir is set, write only Markdown and skip .paperlm.json/.chunks.jsonl.",
    )
    parser.add_argument("--workers", type=int, default=1, help="Number of reusable workers.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Number of PDFs submitted per pool batch. Default: same as --workers.",
    )
    parser.add_argument("--timeout-s", type=float, default=300.0)
    parser.add_argument("--max-rss-mb-hard", type=float, default=6144.0)
    parser.add_argument(
        "--engine",
        choices=["auto", "docling", "ocr", "fallback"],
        default="docling",
    )
    parser.add_argument("--enable-ocr", action="store_true")
    parser.add_argument("--enable-formula", action="store_true")
    parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used for worker subprocesses.",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Return exit code 0 even if some rows fail. Failure details are still emitted in JSONL.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Emit one aggregate JSON summary to stderr after processing.",
    )
    parser.add_argument(
        "--worker-command",
        help=argparse.SUPPRESS,
    )
    return parser


def run_batch(
    items: list[BatchItem],
    *,
    args: argparse.Namespace,
    output_stream: TextIO,
) -> dict[str, Any]:
    if args.workers <= 0:
        raise ValueError("--workers must be > 0")
    if args.timeout_s <= 0:
        raise ValueError("--timeout-s must be > 0")
    if args.max_rss_mb_hard <= 0:
        raise ValueError("--max-rss-mb-hard must be > 0")

    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    batch_size = args.batch_size if args.batch_size > 0 else args.workers
    counts: dict[str, Any] = {
        "total": 0,
        "ok": 0,
        "failed": 0,
        "elapsed_sum_s": 0.0,
        "max_peak_rss_mb": None,
    }
    worker_command = shlex.split(args.worker_command) if args.worker_command else None

    pool = DoclingWorkerPool(
        num_workers=args.workers,
        timeout_s=args.timeout_s,
        max_rss_mb_hard=args.max_rss_mb_hard,
        engine=args.engine,
        enable_ocr=args.enable_ocr,
        enable_formula=args.enable_formula,
        python_executable=args.python_executable,
        worker_command=worker_command,
    )
    try:
        item_offset = 0
        for batch in _chunks(items, batch_size):
            results = _convert_batch(pool, batch)
            for local_index, (item, result) in enumerate(zip(batch, results, strict=True)):
                global_index = item_offset + local_index
                row = _result_row(
                    item,
                    result,
                    output_dir=output_dir,
                    index=global_index,
                    include_markdown=args.include_markdown,
                    write_sidecars=not args.no_sidecars,
                )
                output_stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                output_stream.flush()
                counts["total"] += 1
                if row["status"] == "ok":
                    counts["ok"] += 1
                else:
                    counts["failed"] += 1
                counts["elapsed_sum_s"] = round(
                    float(counts["elapsed_sum_s"]) + _float_value(row.get("elapsed_s")),
                    3,
                )
                peak_rss = _optional_float(row.get("peak_rss_mb"))
                if peak_rss is not None:
                    current = _optional_float(counts.get("max_peak_rss_mb"))
                    counts["max_peak_rss_mb"] = peak_rss if current is None else max(current, peak_rss)
            item_offset += len(batch)
    finally:
        pool.close()

    return counts


def _convert_batch(pool: DoclingWorkerPool, items: list[BatchItem]) -> list[WorkerPoolResult]:
    existing_paths = [item.pdf_path for item in items if Path(item.pdf_path).exists()]
    converted_iter = iter(pool.convert_many(existing_paths)) if existing_paths else iter(())

    results: list[WorkerPoolResult] = []
    for item in items:
        if Path(item.pdf_path).exists():
            results.append(next(converted_iter))
        else:
            results.append(
                WorkerPoolResult(
                    status="error",
                    pdf_path=item.pdf_path,
                    elapsed_s=0.0,
                    engine_used="failed",
                    error=f"PDF not found: {item.pdf_path}",
                )
            )
    return results


def _result_row(
    item: BatchItem,
    result: WorkerPoolResult,
    *,
    output_dir: Path | None,
    index: int,
    include_markdown: bool,
    write_sidecars: bool,
) -> dict[str, Any]:
    artifact_paths = _write_artifacts(
        result,
        output_dir=output_dir,
        index=index,
        write_sidecars=write_sidecars,
    )
    formula_stats = _formula_stats(result.paperlm_dict)
    row: dict[str, Any] = {
        "id": item.item_id,
        "pdf_path": result.pdf_path,
        "status": result.status,
        "elapsed_s": result.elapsed_s,
        "engine_used": result.engine_used,
        "worker_index": result.worker_index,
        "peak_rss_mb": result.peak_rss_mb,
        "chars": len(result.markdown),
        "block_count": _block_count(result.paperlm_dict),
        "formula_detected": formula_stats["detected"],
        "formula_extracted": formula_stats["extracted"],
        "formula_placeholders": formula_stats["placeholders"],
        "warnings": result.warnings,
        "error": result.error,
        **artifact_paths,
    }
    if include_markdown:
        row["markdown"] = result.markdown
    return row


def _write_artifacts(
    result: WorkerPoolResult,
    *,
    output_dir: Path | None,
    index: int,
    write_sidecars: bool,
) -> dict[str, str | None]:
    paths: dict[str, str | None] = {
        "markdown_path": None,
        "paperlm_json_path": None,
        "chunks_jsonl_path": None,
    }
    if output_dir is None:
        return paths

    stem = _artifact_stem(index, result.pdf_path)
    markdown_path = output_dir / f"{stem}.md"
    markdown_path.write_text(result.markdown, encoding="utf-8")
    paths["markdown_path"] = str(markdown_path)

    if write_sidecars and result.paperlm_dict is not None:
        paperlm_json_path = output_dir / f"{stem}.paperlm.json"
        paperlm_json_path.write_text(
            json.dumps(result.paperlm_dict, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        paths["paperlm_json_path"] = str(paperlm_json_path)

    if write_sidecars and result.paperlm_chunks_jsonl:
        chunks_path = output_dir / f"{stem}.chunks.jsonl"
        chunks_path.write_text(result.paperlm_chunks_jsonl, encoding="utf-8")
        paths["chunks_jsonl_path"] = str(chunks_path)

    return paths


def _artifact_stem(index: int, pdf_path: str) -> str:
    raw = Path(pdf_path).stem or "document"
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw).strip("_")
    return f"{index:05d}_{safe or 'document'}"


def _block_count(paperlm_dict: dict[str, Any] | None) -> int:
    if not paperlm_dict:
        return 0
    block_count = paperlm_dict.get("block_count")
    if isinstance(block_count, int):
        return block_count
    blocks = paperlm_dict.get("blocks")
    return len(blocks) if isinstance(blocks, list) else 0


def _formula_stats(paperlm_dict: dict[str, Any] | None) -> dict[str, int]:
    fallback = {"detected": 0, "extracted": 0, "placeholders": 0}
    if not paperlm_dict:
        return fallback
    metadata = paperlm_dict.get("metadata")
    if not isinstance(metadata, dict):
        return fallback
    formula = metadata.get("formula")
    if not isinstance(formula, dict):
        return fallback
    return {
        "detected": _int_value(formula.get("detected")),
        "extracted": _int_value(formula.get("extracted")),
        "placeholders": _int_value(formula.get("placeholders")),
    }


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _float_value(value: Any) -> float:
    parsed = _optional_float(value)
    return parsed if parsed is not None else 0.0


def _optional_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_items(args: argparse.Namespace) -> list[BatchItem]:
    items = [BatchItem(pdf_path=path) for path in args.pdf_paths]
    if args.input_jsonl:
        items.extend(_read_jsonl_items(args.input_jsonl))
    return items


def _read_jsonl_items(path: str) -> list[BatchItem]:
    stream: Iterable[str]
    close_stream = False
    if path == "-":
        stream = sys.stdin
    else:
        fh = Path(path).open("r", encoding="utf-8")
        stream = fh
        close_stream = True

    try:
        items: list[BatchItem] = []
        for line_no, line in enumerate(stream, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
            items.append(_item_from_payload(payload, source=f"{path}:{line_no}"))
        return items
    finally:
        if close_stream:
            fh.close()


def _item_from_payload(payload: Any, *, source: str) -> BatchItem:
    if isinstance(payload, str):
        return BatchItem(pdf_path=payload)
    if isinstance(payload, dict):
        raw_path = payload.get("pdf_path") or payload.get("path") or payload.get("file")
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError(f"{source}: object must include pdf_path/path/file")
        raw_id = payload.get("id")
        return BatchItem(pdf_path=raw_path, item_id=str(raw_id) if raw_id is not None else None)
    raise ValueError(f"{source}: expected string path or object")


def _open_output_jsonl(path: str) -> TextIO:
    if path == "-":
        return sys.stdout
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path.open("w", encoding="utf-8")


def _chunks(items: list[BatchItem], size: int) -> Iterable[list[BatchItem]]:
    if size <= 0:
        raise ValueError("batch size must be > 0")
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
