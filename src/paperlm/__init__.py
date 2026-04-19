"""Public import alias for paperlm.

The implementation package remains ``markitdown_paperlm`` for this release
so existing plugin entry points and internal imports stay stable.
"""

import importlib
import sys

from markitdown_paperlm import (
    __plugin_interface_version__,
    __version__,
    ir_to_chunks_jsonl,
    ir_to_dict,
    ir_to_json,
    register_converters,
)

_SUBMODULE_ALIASES = (
    "_pdf_converter",
    "_plugin",
    "cli",
    "cli.batch",
    "engines",
    "engines.base",
    "engines.docling_adapter",
    "engines.fallback_adapter",
    "engines.ocr_adapter",
    "ir",
    "router",
    "serializers",
    "serializers.captions",
    "serializers.front_matter",
    "serializers.json_sidecar",
    "serializers.markdown",
    "serializers.reading_order",
    "serializers.tables",
    "utils",
    "utils.scanned_detector",
    "workers",
    "workers.docling_pool",
)

for _submodule in _SUBMODULE_ALIASES:
    sys.modules[f"{__name__}.{_submodule}"] = importlib.import_module(
        f"markitdown_paperlm.{_submodule}"
    )

__all__ = [
    "__version__",
    "__plugin_interface_version__",
    "register_converters",
    "ir_to_chunks_jsonl",
    "ir_to_dict",
    "ir_to_json",
]
