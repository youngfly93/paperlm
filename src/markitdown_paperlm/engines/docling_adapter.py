"""Docling engine adapter: DoclingDocument → IR.

Docling is the default engine (MIT licensed, CPU-capable).
This adapter walks DoclingDocument.iterate_items() and maps each
DocItemLabel to a Block in our local IR.

**Formula handling**: Docling's default pipeline detects formula *regions*
but does not extract LaTeX (the text attribute is empty). Passing
``enable_formula=True`` turns on the CodeFormulaV2 VLM to produce LaTeX —
this adds ~500 MB of model weight and noticeably slows conversion, so it
is opt-in. When disabled, formula blocks are still emitted but with a
placeholder.

**Inline vs block formula heuristic**: We compare the formula's bbox
height to the median paragraph height on the same page. Ratios above
``_INLINE_BLOCK_RATIO`` mark the formula as a display (block) equation;
anything smaller is treated as inline.
"""

from __future__ import annotations

import io
import logging
import statistics
from collections import defaultdict
from typing import BinaryIO

from markitdown_paperlm.ir import IR, BBox, Block, BlockType

logger = logging.getLogger(__name__)

# Formulas whose bbox is >= this factor of the page's median paragraph
# height are rendered as display (block) equations. Determined empirically
# on a 27-page bioRxiv paper (paragraph median ≈ 8 pt, display formulas
# were 22-34 pt ⇒ ratios 2.8× and 4.3×).
_INLINE_BLOCK_RATIO = 1.5


# DocItemLabel string values observed in docling 2.90.
# Reference: docling-core DocItemLabel enum.
_LABEL_TO_BLOCKTYPE: dict[str, BlockType] = {
    "title": BlockType.TITLE,
    "section_header": BlockType.HEADING,
    "text": BlockType.PARAGRAPH,
    "paragraph": BlockType.PARAGRAPH,
    "caption": BlockType.CAPTION,
    "picture": BlockType.FIGURE,
    "figure": BlockType.FIGURE,
    "table": BlockType.TABLE,
    "formula": BlockType.FORMULA,
    "code": BlockType.CODE,
    "list_item": BlockType.LIST_ITEM,
    "footnote": BlockType.FOOTNOTE,
}

# Labels we drop entirely (page running heads, page numbers, …).
_FURNITURE_LABELS = {
    "page_header",
    "page_footer",
    "footer",
    "page_number",
}


class DoclingAdapter:
    name = "docling"

    # Lazy-init class-level cache. Keyed by enable_formula so the same
    # adapter instance can be reused for both modes.
    _converters: dict[bool, object] = {}

    def __init__(self, enable_formula: bool = False) -> None:
        """
        Args:
            enable_formula: Turn on CodeFormulaV2 LaTeX extraction. Adds
                model weight + latency; leave False for fast baseline.
        """
        self.enable_formula = enable_formula

    def is_available(self) -> bool:
        try:
            import docling.document_converter  # noqa: F401
        except ImportError:
            return False
        return True

    def _get_converter(self):
        key = bool(self.enable_formula)
        cached = DoclingAdapter._converters.get(key)
        if cached is not None:
            return cached

        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        logger.info(
            "Initializing Docling DocumentConverter (enable_formula=%s) — "
            "first call is slow due to model downloads",
            key,
        )

        if key:
            pipeline_opts = PdfPipelineOptions()
            pipeline_opts.do_formula_enrichment = True
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts)
                }
            )
        else:
            converter = DocumentConverter()

        DoclingAdapter._converters[key] = converter
        return converter

    def convert(self, pdf_stream: BinaryIO) -> IR:
        from docling.datamodel.base_models import DocumentStream

        cur = pdf_stream.tell()
        pdf_bytes = io.BytesIO(pdf_stream.read())
        pdf_stream.seek(cur)

        converter = self._get_converter()
        source = DocumentStream(name="input.pdf", stream=pdf_bytes)
        result = converter.convert(source)
        return self._docling_to_ir(result.document)

    def _docling_to_ir(self, doc) -> IR:
        ir = IR(engine_used=self.name)
        order = 0

        # First pass: collect per-page median paragraph height for
        # inline-formula detection.
        page_medians = _page_paragraph_medians(doc)

        for item, _depth in doc.iterate_items():
            label = str(getattr(item, "label", "")).lower()
            if label in _FURNITURE_LABELS:
                continue

            block_type = _LABEL_TO_BLOCKTYPE.get(label)
            if block_type is None:
                # Unknown label — drop into PARAGRAPH if it has text.
                if getattr(item, "text", None):
                    block_type = BlockType.PARAGRAPH
                else:
                    continue

            block = self._item_to_block(item, block_type, order, page_medians)
            if block is not None:
                ir.blocks.append(block)
                order += 1

        # Formula-enrichment pipeline should populate text; if it's disabled
        # we saw formulas without LaTeX — warn the caller so they know why.
        empty_formulas = [b for b in ir.blocks if b.type == BlockType.FORMULA and not b.content]
        if empty_formulas and not self.enable_formula:
            ir.warnings.append(
                f"{len(empty_formulas)} formula region(s) detected but LaTeX "
                "not extracted. Pass paperlm_enable_formula=True to MarkItDown "
                "for LaTeX recognition."
            )

        # Post-processing pipeline, ordered from layout-preserving to
        # semantic: reading-order → table merge → caption link.
        from markitdown_paperlm.serializers.captions import (
            link_captions,
            reorder_captions_after_targets,
        )
        from markitdown_paperlm.serializers.front_matter import normalize_front_matter
        from markitdown_paperlm.serializers.reading_order import (
            repair_two_column_order,
        )
        from markitdown_paperlm.serializers.tables import merge_cross_page_tables

        # 1. Repair two-column reading order BEFORE table/caption pairing so
        #    that adjacency is meaningful.
        ir.blocks = repair_two_column_order(ir.blocks)

        # 2. Keep the Markdown lead title-first when Docling emits affiliation
        #    or preprint furniture before the title on page 1.
        ir.blocks = normalize_front_matter(ir.blocks)

        # 3. Stitch tables split across page boundaries back together.
        ir.blocks = merge_cross_page_tables(ir.blocks)

        # 4. Pair figures/tables with captions and move captions adjacent
        #    to their target blocks.
        link_captions(ir.blocks)
        ir.blocks = reorder_captions_after_targets(ir.blocks)

        return ir

    def _item_to_block(
        self,
        item,
        block_type: BlockType,
        order: int,
        page_medians: dict[int, float],
    ) -> Block | None:
        attrs: dict = {}
        bbox = _extract_bbox(item)

        if block_type == BlockType.TABLE:
            content, rows = _render_table(item)
            attrs["rows"] = rows
        elif block_type == BlockType.FIGURE:
            content = ""  # figure content is visual; caption may be separate
            attrs["image_path"] = None  # Week 3 will populate when we persist images
        elif block_type == BlockType.FORMULA:
            content = getattr(item, "text", "") or ""
            attrs["inline"] = _is_inline_formula(bbox, page_medians)
        elif block_type == BlockType.HEADING:
            content = getattr(item, "text", "") or ""
            # Docling's section_header doesn't expose level directly; default to 2.
            # Week 3 will infer level from font-size or tree depth.
            attrs["level"] = 2
        else:
            content = getattr(item, "text", "") or ""

        if not content and block_type not in (BlockType.FIGURE, BlockType.FORMULA):
            return None

        return Block(
            type=block_type,
            content=content.strip() if isinstance(content, str) else content,
            bbox=bbox,
            reading_order=order,
            attrs=attrs,
        )


def _page_paragraph_medians(doc) -> dict[int, float]:
    """Return {page_no: median paragraph height}.

    Used as a per-page reference scale for classifying formulas as inline
    (close to text height) vs block (multiples of text height).
    """
    heights_by_page: dict[int, list[float]] = defaultdict(list)
    for item, _ in doc.iterate_items():
        if str(getattr(item, "label", "")).lower() != "text":
            continue
        prov = getattr(item, "prov", None)
        if not prov:
            continue
        first = prov[0] if isinstance(prov, list) else prov
        bbox = getattr(first, "bbox", None)
        page_no = getattr(first, "page_no", None)
        if bbox is None or page_no is None:
            continue
        try:
            h = abs(float(bbox.b) - float(bbox.t))
        except (AttributeError, TypeError, ValueError):
            continue
        if h > 0:
            heights_by_page[int(page_no)].append(h)

    return {
        page: statistics.median(heights)
        for page, heights in heights_by_page.items()
        if heights
    }


def _is_inline_formula(bbox: BBox | None, page_medians: dict[int, float]) -> bool:
    """Classify a formula as inline using bbox height vs page text median.

    Fall-backs:
      - No bbox or no page median → default to block (safer for display
        equations which are the common case in scientific PDFs).
    """
    if bbox is None:
        return False
    median = page_medians.get(bbox.page)
    if not median or median <= 0:
        return False
    height = abs(bbox.y1 - bbox.y0)
    return height < _INLINE_BLOCK_RATIO * median


def _extract_bbox(item) -> BBox | None:
    prov = getattr(item, "prov", None)
    if not prov:
        return None
    first = prov[0] if isinstance(prov, list) else prov
    page_no = getattr(first, "page_no", None)
    bbox_obj = getattr(first, "bbox", None)
    if page_no is None or bbox_obj is None:
        return None
    try:
        return BBox(
            page=int(page_no),
            x0=float(bbox_obj.l),
            y0=float(bbox_obj.t),
            x1=float(bbox_obj.r),
            y1=float(bbox_obj.b),
        )
    except (AttributeError, TypeError, ValueError):
        return None


def _render_table(table_item) -> tuple[str, list[list[str]]]:
    """Extract 2D cell data from a Docling table and render it as GFM.

    The heavy lifting (escaping, width alignment, CJK handling) lives in
    :mod:`markitdown_paperlm.serializers.tables`. This function is only
    responsible for Docling → ``list[list[str]]`` extraction.
    """
    from markitdown_paperlm.serializers.tables import render_gfm_table

    rows: list[list[str]] = []
    data = getattr(table_item, "data", None)
    if data is None:
        return ("", [])

    grid = getattr(data, "grid", None) or getattr(data, "table_cells", None)
    if grid is None:
        return ("", [])

    for row in grid:
        row_cells = []
        for cell in row:
            text = getattr(cell, "text", "") or ""
            row_cells.append(text)
        rows.append(row_cells)

    return (render_gfm_table(rows), rows)
