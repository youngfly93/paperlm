"""Plugin registration for paperlm.

Registers a PDF converter with priority=-1.0 to run BEFORE the built-in
MarkItDown PdfConverter (priority=0.0), effectively replacing it when
the plugin is enabled.

Pattern mirrored from markitdown-ocr/_plugin.py.
"""

from typing import Any

from markitdown import MarkItDown

from markitdown_paperlm._pdf_converter import PaperLMPdfConverter

__plugin_interface_version__ = 1


def register_converters(markitdown: MarkItDown, **kwargs: Any) -> None:
    """Register paperlm's PDF converter with MarkItDown.

    Called during MarkItDown construction when plugins are enabled.

    Accepted kwargs (all optional):
        paperlm_engine: "auto" | "docling" | "ocr" | "fallback". Default "auto".
        paperlm_enable_ocr: bool. Default True (used only when [ocr] extra installed).
        paperlm_enable_formula: bool. Default False; formula LaTeX extraction is opt-in.
    """
    engine = kwargs.get("paperlm_engine", "auto")
    enable_ocr = kwargs.get("paperlm_enable_ocr", True)
    enable_formula = kwargs.get("paperlm_enable_formula", False)

    # Priority -1.0 runs BEFORE built-in PdfConverter (priority 0.0).
    # Mirrors markitdown-ocr's strategy at packages/markitdown-ocr/src/markitdown_ocr/_plugin.py:52
    PRIORITY_PAPERLM = -1.0

    markitdown.register_converter(
        PaperLMPdfConverter(
            engine=engine,
            enable_ocr=enable_ocr,
            enable_formula=enable_formula,
        ),
        priority=PRIORITY_PAPERLM,
    )
