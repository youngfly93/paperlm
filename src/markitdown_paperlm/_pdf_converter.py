"""PaperLMPdfConverter — replaces built-in MarkItDown PdfConverter.

Thin wrapper over EngineRouter: accept PDF → route → serialize → wrap.
All engine-selection logic lives in router.py; all block→markdown
logic lives in serializers/markdown.py.
"""

from __future__ import annotations

import io
from typing import Any, BinaryIO, cast

from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo

from markitdown_paperlm.router import EngineRouter
from markitdown_paperlm.serializers.json_sidecar import (
    ir_to_chunks_jsonl,
    ir_to_dict,
    ir_to_json,
)
from markitdown_paperlm.serializers.markdown import MarkdownSerializer

ACCEPTED_MIME_TYPE_PREFIXES = [
    "application/pdf",
    "application/x-pdf",
]
ACCEPTED_FILE_EXTENSIONS = [".pdf"]


class PaperLMPdfConverter(DocumentConverter):
    """PDF converter that dispatches to Docling / OCR / pdfminer via EngineRouter.

    Non-stable attributes attached to the result:
        result.ir           — the full IR (blocks, warnings, engine_used)
        result.engine_used  — shortcut for ir.engine_used
        result.paperlm_dict — JSON-serializable IR dictionary
        result.paperlm_json — JSON sidecar text
        result.paperlm_chunks_jsonl — text-bearing blocks as JSONL

    Only result.markdown / result.title are part of MarkItDown's stable API.
    """

    def __init__(
        self,
        engine: str = "auto",
        enable_ocr: bool = True,
        enable_formula: bool = False,
    ) -> None:
        self.engine = engine
        self.enable_ocr = enable_ocr
        self.enable_formula = enable_formula
        self._router = EngineRouter(
            engine=engine,
            enable_ocr=enable_ocr,
            enable_formula=enable_formula,
        )
        self._serializer = MarkdownSerializer()

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        mimetype = (stream_info.mimetype or "").lower()
        extension = (stream_info.extension or "").lower()
        if extension in ACCEPTED_FILE_EXTENSIONS:
            return True
        return any(mimetype.startswith(prefix) for prefix in ACCEPTED_MIME_TYPE_PREFIXES)

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> DocumentConverterResult:
        assert isinstance(file_stream, io.IOBase)

        ir = self._router.convert(file_stream)
        markdown = self._serializer.render(ir)

        result = DocumentConverterResult(markdown=markdown)
        # Non-stable API — see class docstring.
        result_ext = cast(Any, result)
        result_ext.ir = ir
        result_ext.engine_used = ir.engine_used
        result_ext.paperlm_dict = ir_to_dict(ir)
        result_ext.paperlm_json = ir_to_json(ir)
        result_ext.paperlm_chunks_jsonl = ir_to_chunks_jsonl(ir)
        return result
