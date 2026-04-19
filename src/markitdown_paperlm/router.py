"""Engine routing and degradation chain.

Rules (v0.0.x):

    engine="auto" (default):
        1. Sample the PDF for a text layer (utils.scanned_detector).
        2. If scanned (no text) AND OCR is available → prefer OCRAdapter.
           This matters because Docling's bundled OCR misidentifies
           Chinese as Cyrillic (verified in Week 1 Day 2 benchmark),
           so PaddleOCR gives materially better Chinese results.
        3. Otherwise → DoclingAdapter first.
        4. Anything else / empty result / crash → next engine in chain.
        5. FallbackAdapter (pdfminer) always closes the chain.

    engine="docling" | "ocr" | "fallback":
        Force that single engine; fallback still kicks in on exception
        so the caller always receives *something*.

The router is deliberately stream-safe: it seeks(0) before each
attempt so adapters see a fresh position.
"""

from __future__ import annotations

import io
import logging
from typing import BinaryIO

from markitdown_paperlm.engines.base import EngineAdapter
from markitdown_paperlm.engines.fallback_adapter import FallbackAdapter
from markitdown_paperlm.ir import IR
from markitdown_paperlm.utils.scanned_detector import is_scanned_pdf

logger = logging.getLogger(__name__)

VALID_ENGINES = {"auto", "docling", "ocr", "fallback"}


class EngineRouter:
    """Dispatch PDF streams to the right engine with graceful degradation."""

    def __init__(
        self,
        engine: str = "auto",
        enable_ocr: bool = True,
        enable_formula: bool = False,
    ) -> None:
        if engine not in VALID_ENGINES:
            raise ValueError(
                f"Unknown engine {engine!r}; expected one of {sorted(VALID_ENGINES)}"
            )
        self.engine = engine
        self.enable_ocr = enable_ocr
        self.enable_formula = enable_formula

    def convert(self, pdf_stream: BinaryIO) -> IR:
        """Route the stream to the appropriate engine and return an IR.

        Always returns a valid IR; on catastrophic failure the IR has
        warnings set and zero blocks, but never raises.
        """
        # Buffer once — adapters may read repeatedly.
        pdf_bytes = _materialize(pdf_stream)

        # In auto mode, cheaply probe whether the PDF is scanned so we
        # can prefer PaddleOCR over Docling for image-only Chinese docs.
        is_scanned = False
        scan_reason = ""
        if self.engine == "auto":
            pdf_bytes.seek(0)
            res = is_scanned_pdf(pdf_bytes)
            is_scanned = res.is_scanned
            scan_reason = res.reason

        chain = self._build_chain(is_scanned=is_scanned)
        all_warnings: list[str] = []
        if self.engine == "auto":
            all_warnings.append(f"scanned_check: {scan_reason}")

        for adapter in chain:
            if not adapter.is_available():
                all_warnings.append(f"{adapter.name}: not available (skipped)")
                continue
            try:
                pdf_bytes.seek(0)
                ir = adapter.convert(pdf_bytes)
                # Prepend previous-adapter warnings so callers see the trail.
                ir.warnings = all_warnings + list(ir.warnings)
                # Accept result if it produced any blocks OR is the last chain entry
                if ir.blocks or adapter is chain[-1]:
                    return ir
                # Empty result from an intermediate engine → try next
                all_warnings.extend(f"{adapter.name}: {w}" for w in ir.warnings)
                all_warnings.append(f"{adapter.name}: empty result, trying next")
            except Exception as exc:
                logger.warning("%s raised, continuing chain: %s", adapter.name, exc)
                all_warnings.append(f"{adapter.name}: {exc}")

        # Nothing in the chain worked — return a bare IR.
        return IR(engine_used="failed", warnings=all_warnings)

    def _build_chain(self, *, is_scanned: bool = False) -> list[EngineAdapter]:
        """Return adapters to try, in order. Fallback is always last.

        When called without is_scanned information (e.g. by tests or forced
        engines), the order falls back to: Docling → OCR → FallbackAdapter.
        """
        chain: list[EngineAdapter] = []

        docling = (
            _try_load_docling(enable_formula=self.enable_formula)
            if self.engine in ("auto", "docling")
            else None
        )
        ocr = None
        if (self.engine == "auto" and self.enable_ocr) or self.engine == "ocr":
            ocr = _try_load_ocr()

        if self.engine == "auto" and is_scanned:
            # Scanned docs: OCR first for materially better Chinese results.
            if ocr is not None:
                chain.append(ocr)
            if docling is not None:
                chain.append(docling)
        else:
            if docling is not None:
                chain.append(docling)
            if ocr is not None:
                chain.append(ocr)

        # Fallback is always last and always present.
        chain.append(FallbackAdapter())
        return chain


def _materialize(stream: BinaryIO) -> io.BytesIO:
    """Read the stream into a BytesIO so adapters can seek freely."""
    cur = stream.tell()
    data = stream.read()
    stream.seek(cur)
    return io.BytesIO(data)


def _try_load_docling(enable_formula: bool = False) -> EngineAdapter | None:
    try:
        from markitdown_paperlm.engines.docling_adapter import DoclingAdapter
    except ImportError:
        return None
    adapter = DoclingAdapter(enable_formula=enable_formula)
    return adapter if adapter.is_available() else None


def _try_load_ocr() -> EngineAdapter | None:
    try:
        from markitdown_paperlm.engines.ocr_adapter import OCRAdapter
    except ImportError:
        return None
    adapter = OCRAdapter()
    return adapter if adapter.is_available() else None
