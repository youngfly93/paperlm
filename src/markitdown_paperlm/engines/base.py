"""Engine adapter abstraction.

All engines (Docling, PaddleOCR, pdfminer fallback, future Marker/MinerU)
implement this Protocol so the router can treat them uniformly.
"""

from __future__ import annotations

from typing import BinaryIO, Protocol, runtime_checkable

from markitdown_paperlm.ir import IR


@runtime_checkable
class EngineAdapter(Protocol):
    """Contract every PDF-parsing engine must fulfill."""

    name: str

    def is_available(self) -> bool:
        """Return True if this engine's dependencies are importable.

        Should not trigger heavy model loads — only verify imports succeed.
        """
        ...

    def convert(self, pdf_stream: BinaryIO) -> IR:
        """Parse a PDF stream and return IR.

        Must not raise for recoverable errors — use IR.warnings instead.
        Should reset stream position after reading.
        """
        ...
