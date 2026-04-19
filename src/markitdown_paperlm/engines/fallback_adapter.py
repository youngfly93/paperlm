"""Fallback engine adapter: pdfminer text extraction.

The lowest-cost engine in the router chain. Requires only pdfminer.six,
which is declared as a core dependency of this package (see pyproject.toml)
AND is already a transitive dependency of MarkItDown itself, so in any
reasonable install it is available. It produces a minimal IR (one
PARAGRAPH block per page-break-separated chunk) so downstream serializers
always have something to render.
"""

from __future__ import annotations

import logging
from typing import BinaryIO

from markitdown_paperlm.ir import IR, Block, BlockType

logger = logging.getLogger(__name__)


class FallbackAdapter:
    """Minimal pdfminer-based adapter.

    Availability depends on ``pdfminer.six`` being importable. It ships as
    a core dependency of ``paperlm`` so a standard install always
    has it — but check ``is_available()`` if you are running in a stripped
    environment.
    """

    name = "pdfminer"

    def is_available(self) -> bool:
        try:
            import pdfminer.high_level  # noqa: F401
        except ImportError:
            return False
        return True

    def convert(self, pdf_stream: BinaryIO) -> IR:
        import pdfminer.high_level

        cur = pdf_stream.tell()
        try:
            pdf_stream.seek(0)
            try:
                text = pdfminer.high_level.extract_text(pdf_stream) or ""
            except Exception as exc:
                logger.error("pdfminer.extract_text failed: %s", exc)
                return IR(
                    engine_used=self.name,
                    warnings=[f"pdfminer failed: {exc}"],
                )
        finally:
            pdf_stream.seek(cur)

        text = text.strip()
        if not text:
            return IR(
                engine_used=self.name,
                warnings=[
                    "no text extracted — likely scanned PDF; "
                    "install paperlm[ocr] to enable OCR"
                ],
            )

        # Week 1 MVP rendering: one block per page-break-separated chunk.
        # Good enough as a fallback; downstream serializers emit paragraphs.
        blocks: list[Block] = []
        for order, chunk in enumerate(_split_into_paragraphs(text)):
            blocks.append(
                Block(
                    type=BlockType.PARAGRAPH,
                    content=chunk,
                    reading_order=order,
                )
            )

        return IR(engine_used=self.name, blocks=blocks)


def _split_into_paragraphs(text: str) -> list[str]:
    """Split pdfminer output into paragraphs on blank lines.

    pdfminer separates pages with form-feed (\\f). We normalize both
    page breaks and multi-blank-line gaps into paragraph boundaries.
    """
    normalized = text.replace("\f", "\n\n")
    chunks = [p.strip() for p in normalized.split("\n\n")]
    return [c for c in chunks if c]
