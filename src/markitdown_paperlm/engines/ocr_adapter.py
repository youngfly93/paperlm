"""Local OCR engine adapter using PaddleOCR (Apache-2.0).

Handles scanned PDFs where Docling's built-in OCR performs poorly on
Chinese text (Day 2 benchmark showed Docling's OCR misidentified
Chinese characters as Cyrillic). PaddleOCR's PP-OCRv5 has strong
Chinese+English multilingual support.

Adapter lifecycle:
  - Optional extra (pip install paperlm[ocr])
  - Lazy-initializes PaddleOCR on first convert() call (model download)
  - Renders each PDF page via pypdfium2, runs OCR, emits one PARAGRAPH
    Block per detected text line (ordered by y-coordinate)

Model variant tradeoff (Week 4 Day 1 probe):

    variant    time/page    peak RSS    quality
    mobile     ~15 s        ~2.7 GB     45 lines   ← default
    server     ~27 s        ~10.3 GB    45 lines   (no quality gain on our
                                                    Chinese bioinformatics
                                                    fixture, 74% more RSS)

``low_memory=True`` additionally enables per-page gc + paddle's
``naive_best_fit`` allocator, bringing peak RSS down to ~2.0 GB at a
small latency cost. Use when your workers have <4 GB RAM.

Licensing: PaddleOCR and PaddlePaddle are both Apache-2.0 — safe to
include in commercial pipelines.
"""

from __future__ import annotations

import gc
import logging
import os
from typing import Any, BinaryIO

from markitdown_paperlm.ir import IR, BBox, Block, BlockType

logger = logging.getLogger(__name__)

# Default rasterization DPI. Mobile models at 150 dpi gave full quality
# on our test fixture; bumping to 200 dpi helps on very small fonts but
# multiplies image area by 1.8×.
RENDER_DPI = 150

# Page-level mean confidence below this threshold is surfaced as an IR warning.
LOW_CONFIDENCE_THRESHOLD = 0.75


class OCRAdapter:
    """PaddleOCR-powered adapter for scanned PDFs."""

    name = "paddleocr"

    # Class-level cache keyed by (variant, lang, low_memory) so the same
    # adapter can be reused when callers switch configuration.
    _ocr_cache: dict[tuple, Any] = {}

    def __init__(
        self,
        lang: str = "ch",
        *,
        variant: str = "mobile",
        low_memory: bool = False,
        render_dpi: int | None = None,
    ) -> None:
        """
        Args:
            lang: PaddleOCR language code. "ch" handles Chinese + English.
                  Only used when ``variant="server"``; mobile variant uses
                  explicit model names instead.
            variant: "mobile" (default) loads PP-OCRv5_mobile_* (~250 MB
                     total, ~2.7 GB peak RSS). "server" loads the larger
                     PP-OCRv5_server_* (~10 GB peak RSS, no measurable
                     quality gain on our fixtures).
            low_memory: If True, call gc.collect() after each page and set
                     paddle's ``naive_best_fit`` allocator before import.
                     Further reduces RSS by ~700 MB at some latency cost.
            render_dpi: Override rasterization DPI (default 150). Lower
                     values are faster; higher values may improve
                     recognition of very small fonts.
        """
        if variant not in ("mobile", "server"):
            raise ValueError(f"variant must be 'mobile' or 'server', got {variant!r}")
        self.lang = lang
        self.variant = variant
        self.low_memory = low_memory
        self.render_dpi = render_dpi or RENDER_DPI

    def is_available(self) -> bool:
        try:
            import paddle  # noqa: F401
            import paddleocr  # noqa: F401
            import pypdfium2  # noqa: F401
        except ImportError:
            return False
        return True

    def _get_ocr(self) -> Any:
        key = (self.variant, self.lang, self.low_memory)
        cached = OCRAdapter._ocr_cache.get(key)
        if cached is not None:
            return cached

        # Paddle reads these env vars at import time, so set them before.
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        if self.low_memory:
            os.environ.setdefault("FLAGS_allocator_strategy", "naive_best_fit")
            os.environ.setdefault("FLAGS_fraction_of_cpu_memory_to_use", "0")

        from paddleocr import PaddleOCR

        logger.info(
            "Initializing PaddleOCR (variant=%s, lang=%s, low_memory=%s) — "
            "first call downloads models",
            self.variant,
            self.lang,
            self.low_memory,
        )

        kwargs: dict[str, Any] = dict(
            use_textline_orientation=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
        )
        if self.variant == "mobile":
            kwargs["text_detection_model_name"] = "PP-OCRv5_mobile_det"
            kwargs["text_recognition_model_name"] = "PP-OCRv5_mobile_rec"
        else:
            kwargs["lang"] = self.lang

        inst = PaddleOCR(**kwargs)
        OCRAdapter._ocr_cache[key] = inst
        return inst

    def convert(self, pdf_stream: BinaryIO) -> IR:
        import numpy as np
        import pypdfium2 as pdfium

        cur = pdf_stream.tell()
        try:
            pdf_stream.seek(0)
            pdf_bytes = pdf_stream.read()
        finally:
            pdf_stream.seek(cur)

        ir = IR(
            engine_used=self.name,
            metadata={
                "ocr": {
                    "engine": self.name,
                    "variant": self.variant,
                    "lang": self.lang,
                    "render_dpi": self.render_dpi,
                    "low_memory": self.low_memory,
                    "low_confidence_threshold": LOW_CONFIDENCE_THRESHOLD,
                    "pages": [],
                }
            },
        )

        try:
            ocr = self._get_ocr()
        except Exception as exc:
            logger.error("PaddleOCR init failed: %s", exc)
            return IR(engine_used=self.name, warnings=[f"init failed: {exc}"])

        try:
            pdf = pdfium.PdfDocument(pdf_bytes)
        except Exception as exc:
            logger.error("pypdfium2 failed to open PDF: %s", exc)
            return IR(engine_used=self.name, warnings=[f"pdf open failed: {exc}"])

        scale = self.render_dpi / 72.0
        order = 0

        for page_idx in range(len(pdf)):
            try:
                page = pdf[page_idx]
                pil = page.render(scale=scale).to_pil().convert("RGB")
                page.close()
            except Exception as exc:
                ir.warnings.append(f"page {page_idx + 1} render failed: {exc}")
                continue

            arr = np.array(pil)
            del pil  # release the PIL image ASAP

            try:
                results = ocr.predict(arr)
            except Exception as exc:
                ir.warnings.append(f"page {page_idx + 1} OCR failed: {exc}")
                del arr
                if self.low_memory:
                    gc.collect()
                continue

            # Release the big numpy image before building blocks.
            del arr

            if not results:
                _record_page_confidence(ir, page_idx + 1, [])
                if self.low_memory:
                    gc.collect()
                continue

            page_result = results[0]
            texts = page_result.get("rec_texts") or []
            boxes = page_result.get("rec_boxes")
            scores = page_result.get("rec_scores") or []

            if boxes is not None and hasattr(boxes, "tolist"):
                boxes = boxes.tolist()
            else:
                boxes = list(boxes or [])

            # Sort lines top-to-bottom, left-to-right by box top-left corner.
            # PaddleOCR guarantees these three lists are the same length.
            rows = list(zip(texts, boxes, scores, strict=False))
            rows.sort(key=lambda r: (r[1][1] if r[1] else 0, r[1][0] if r[1] else 0))

            kept_scores: list[float] = []
            for text, box, score in rows:
                text = (text or "").strip()
                if not text:
                    continue
                confidence = float(score) if score is not None else 0.0
                kept_scores.append(confidence)
                bbox = _make_bbox(page_idx + 1, box)
                ir.blocks.append(
                    Block(
                        type=BlockType.PARAGRAPH,
                        content=text,
                        bbox=bbox,
                        reading_order=order,
                        attrs={"ocr_confidence": confidence},
                    )
                )
                order += 1
            _record_page_confidence(ir, page_idx + 1, kept_scores)

            # Let paddle's working buffers recycle between pages.
            del results, page_result
            if self.low_memory:
                gc.collect()

        pdf.close()

        if not ir.blocks:
            ir.warnings.append("OCR produced no text")

        _finalize_ocr_metadata(ir)

        return ir


def _make_bbox(page: int, box: Any) -> BBox | None:
    if not box:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in box[:4])
        return BBox(page=page, x0=x0, y0=y0, x1=x1, y1=y1)
    except (TypeError, ValueError, IndexError):
        return None


def _record_page_confidence(ir: IR, page: int, scores: list[float]) -> None:
    mean_confidence = round(sum(scores) / len(scores), 4) if scores else None
    min_confidence = round(min(scores), 4) if scores else None
    page_meta = {
        "page": page,
        "line_count": len(scores),
        "mean_confidence": mean_confidence,
        "min_confidence": min_confidence,
    }
    ir.metadata.setdefault("ocr", {}).setdefault("pages", []).append(page_meta)

    if mean_confidence is None:
        ir.warnings.append(f"page {page} OCR produced no text")
    elif mean_confidence < LOW_CONFIDENCE_THRESHOLD:
        ir.warnings.append(
            f"page {page} low OCR confidence: {mean_confidence:.2f} "
            f"< {LOW_CONFIDENCE_THRESHOLD:.2f}"
        )


def _finalize_ocr_metadata(ir: IR) -> None:
    ocr_meta = ir.metadata.setdefault("ocr", {})
    pages = ocr_meta.get("pages") or []
    means = [
        float(page["mean_confidence"])
        for page in pages
        if page.get("mean_confidence") is not None
    ]
    if means:
        ocr_meta["mean_confidence"] = round(sum(means) / len(means), 4)
        ocr_meta["min_page_confidence"] = round(min(means), 4)
    else:
        ocr_meta["mean_confidence"] = None
        ocr_meta["min_page_confidence"] = None

    ocr_meta["low_confidence_pages"] = [
        page["page"]
        for page in pages
        if page.get("mean_confidence") is not None
        and float(page["mean_confidence"]) < LOW_CONFIDENCE_THRESHOLD
    ]
    ocr_meta["empty_pages"] = [
        page["page"] for page in pages if page.get("mean_confidence") is None
    ]
