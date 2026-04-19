"""Operational CLI tools for paperlm deployments."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from markitdown_paperlm.workers import DoclingWorkerPool, WorkerPoolResult

VALID_WARMUP_ENGINES = ("docling", "ocr", "fallback")
EXPECTED_ENGINE_USED = {
    "docling": "docling",
    "ocr": "paddleocr",
    "fallback": "pdfminer",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "warmup":
        try:
            return warmup(args=args, output_stream=sys.stdout, error_stream=sys.stderr)
        except ValueError as exc:
            parser.error(str(exc))

    parser.error("missing command")
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="paperlm-tools",
        description="Operational tools for paperlm deployments.",
    )
    subparsers = parser.add_subparsers(dest="command")

    warmup_parser = subparsers.add_parser(
        "warmup",
        help="Preload optional parser/OCR engines in guarded subprocesses.",
        description=(
            "Run a tiny synthetic PDF through selected engines so model downloads "
            "and first-use initialization happen before production traffic."
        ),
    )
    warmup_parser.add_argument(
        "--engine",
        default="docling",
        help="Comma-separated engines to warm up: docling, ocr, fallback. Default: docling.",
    )
    warmup_parser.add_argument("--timeout-s", type=float, default=300.0)
    warmup_parser.add_argument("--max-rss-mb-hard", type=float, default=6144.0)
    warmup_parser.add_argument(
        "--python-executable",
        default=sys.executable,
        help="Python executable used for worker subprocesses.",
    )
    warmup_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit one JSON object per engine instead of human-readable lines.",
    )
    warmup_parser.add_argument(
        "--worker-command",
        help=argparse.SUPPRESS,
    )
    return parser


def warmup(
    *,
    args: argparse.Namespace,
    output_stream: TextIO,
    error_stream: TextIO,
) -> int:
    engines = _parse_engines(args.engine)
    worker_command = shlex.split(args.worker_command) if args.worker_command else None

    rows: list[dict[str, Any]] = []
    exit_code = 0
    with tempfile.TemporaryDirectory(prefix="paperlm-warmup-") as tmpdir:
        pdf_path = Path(tmpdir) / "paperlm_warmup.pdf"
        write_minimal_text_pdf(pdf_path)

        for engine in engines:
            result = _warmup_one_engine(
                engine=engine,
                pdf_path=pdf_path,
                timeout_s=args.timeout_s,
                max_rss_mb_hard=args.max_rss_mb_hard,
                python_executable=args.python_executable,
                worker_command=worker_command,
            )
            row = _warmup_row(engine, result)
            rows.append(row)
            if row["status"] != "ok":
                exit_code = 1

    for row in rows:
        if args.json:
            output_stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            stream = output_stream if row["status"] == "ok" else error_stream
            stream.write(_format_warmup_row(row) + "\n")

    output_stream.flush()
    error_stream.flush()
    return exit_code


def _warmup_one_engine(
    *,
    engine: str,
    pdf_path: Path,
    timeout_s: float,
    max_rss_mb_hard: float,
    python_executable: str,
    worker_command: list[str] | None,
) -> WorkerPoolResult:
    with DoclingWorkerPool(
        num_workers=1,
        timeout_s=timeout_s,
        max_rss_mb_hard=max_rss_mb_hard,
        engine=engine,
        enable_ocr=(engine == "ocr"),
        python_executable=python_executable,
        worker_command=worker_command,
    ) as pool:
        return pool.convert(pdf_path)


def _warmup_row(engine: str, result: WorkerPoolResult) -> dict[str, Any]:
    expected_engine = EXPECTED_ENGINE_USED[engine]
    status = result.status
    error = result.error or "; ".join(result.warnings)

    if result.status == "ok" and result.engine_used != expected_engine:
        status = "error"
        error = (
            f"expected engine_used={expected_engine!r}, got {result.engine_used!r}; "
            f"install the required extra or check engine availability"
        )

    return {
        "engine": engine,
        "status": status,
        "engine_used": result.engine_used,
        "elapsed_s": result.elapsed_s,
        "peak_rss_mb": result.peak_rss_mb,
        "chars": len(result.markdown),
        "warnings": result.warnings,
        "error": error,
    }


def _format_warmup_row(row: dict[str, Any]) -> str:
    if row["status"] == "ok":
        rss = row["peak_rss_mb"]
        rss_text = f", peak_rss_mb={rss}" if rss is not None else ""
        return (
            f"{row['engine']}: ok "
            f"(engine_used={row['engine_used']}, elapsed_s={row['elapsed_s']}{rss_text})"
        )
    return f"{row['engine']}: {row['status']} ({row['error']})"


def _parse_engines(raw: str) -> list[str]:
    engines: list[str] = []
    for part in raw.split(","):
        engine = part.strip().lower()
        if not engine:
            continue
        if engine not in VALID_WARMUP_ENGINES:
            valid = ", ".join(VALID_WARMUP_ENGINES)
            raise ValueError(f"unknown warmup engine {engine!r}; expected one of: {valid}")
        if engine not in engines:
            engines.append(engine)
    if not engines:
        raise ValueError("at least one warmup engine is required")
    return engines


def write_minimal_text_pdf(path: Path) -> None:
    """Write a tiny text-layer PDF with no third-party dependencies."""

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = b"BT /F1 12 Tf 72 72 Td (paperlm warmup) Tj ET\n"
    objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream")

    parts = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in parts))
        parts.append(f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n")

    xref_offset = sum(len(part) for part in parts)
    xref = [b"xref\n0 6\n", b"0000000000 65535 f \n"]
    xref.extend(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets[1:])
    parts.extend(
        [
            *xref,
            b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n",
            str(xref_offset).encode("ascii") + b"\n%%EOF\n",
        ]
    )
    path.write_bytes(b"".join(parts))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
