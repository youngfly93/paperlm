"""JSONL worker process for long-lived Docling-backed conversions.

This module is intentionally small and protocol-oriented. The parent process
owns timeouts/RSS watchdogs; the worker only keeps MarkItDown + paperlm
initialized and answers one JSON line per request.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from typing import Any

from markitdown import MarkItDown

from markitdown_paperlm._plugin import register_converters


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="paperlm Docling JSONL worker")
    parser.add_argument("--engine", default="docling", choices=["auto", "docling", "ocr", "fallback"])
    parser.add_argument("--enable-ocr", action="store_true")
    parser.add_argument("--enable-formula", action="store_true")
    args = parser.parse_args(argv)

    md = MarkItDown()
    register_converters(
        md,
        paperlm_engine=args.engine,
        paperlm_enable_ocr=args.enable_ocr,
        paperlm_enable_formula=args.enable_formula,
    )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _emit({"id": None, "status": "error", "error": f"invalid JSON: {exc}"})
            continue

        request_id = request.get("id")
        if request.get("cmd") == "shutdown":
            _emit({"id": request_id, "status": "shutdown"})
            return 0

        _emit(_convert_one(md, request))

    return 0


def _convert_one(md: MarkItDown, request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id")
    pdf_path = request.get("pdf_path")
    started = time.perf_counter()

    if not isinstance(pdf_path, str) or not pdf_path:
        return {
            "id": request_id,
            "pdf_path": pdf_path or "",
            "status": "error",
            "elapsed_s": 0.0,
            "markdown": "",
            "engine_used": "failed",
            "warnings": [],
            "paperlm_dict": None,
            "paperlm_chunks_jsonl": "",
            "error": "request.pdf_path must be a non-empty string",
        }

    try:
        result = md.convert(pdf_path)
        markdown = getattr(result, "markdown", "") or ""
        paperlm_dict = _json_safe(getattr(result, "paperlm_dict", None))
        warnings = _json_safe(_extract_warnings(result))
        return {
            "id": request_id,
            "pdf_path": pdf_path,
            "status": "ok" if markdown.strip() else "empty",
            "elapsed_s": round(time.perf_counter() - started, 3),
            "markdown": markdown,
            "engine_used": str(getattr(result, "engine_used", "") or ""),
            "warnings": warnings,
            "paperlm_dict": paperlm_dict,
            "paperlm_chunks_jsonl": str(getattr(result, "paperlm_chunks_jsonl", "") or ""),
            "error": "",
        }
    except Exception as exc:  # pragma: no cover - exercised by integration failures
        return {
            "id": request_id,
            "pdf_path": pdf_path,
            "status": "error",
            "elapsed_s": round(time.perf_counter() - started, 3),
            "markdown": "",
            "engine_used": "failed",
            "warnings": [],
            "paperlm_dict": None,
            "paperlm_chunks_jsonl": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _extract_warnings(result: Any) -> list[Any]:
    ir = getattr(result, "ir", None)
    warnings = getattr(ir, "warnings", None)
    if isinstance(warnings, list):
        return warnings
    return []


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
