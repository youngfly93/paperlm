"""paperlm: Scientific PDFs → Markdown, built for LLMs.

A MarkItDown plugin that replaces the built-in PDF converter with
Docling-powered layout analysis, formula-region preservation, and local OCR.
"""

from markitdown_paperlm.__about__ import __version__
from markitdown_paperlm._plugin import (
    __plugin_interface_version__,
    register_converters,
)
from markitdown_paperlm.serializers.json_sidecar import (
    ir_to_chunks_jsonl,
    ir_to_dict,
    ir_to_json,
)

__all__ = [
    "__version__",
    "__plugin_interface_version__",
    "register_converters",
    "ir_to_chunks_jsonl",
    "ir_to_dict",
    "ir_to_json",
]
