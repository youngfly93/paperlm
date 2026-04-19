"""Week 1 smoke tests for plugin import + registration behavior.

Two layers:

  Direct-call tests (always run):
    Call ``register_converters(md)`` on a fresh MarkItDown object. These
    verify the plugin module itself — they do not depend on the package
    being installed via entry_points.

  Entry-point test (skipped when not installed):
    Calling ``MarkItDown(enable_plugins=True)`` relies on MarkItDown's
    ``importlib.metadata.entry_points(group="markitdown.plugin")``
    discovery, which only works once this package is installed (``pip
    install -e .``). Pure source-tree pytest runs will skip it.
"""

from importlib.metadata import entry_points

import pytest
from markitdown import MarkItDown

from markitdown_paperlm import __plugin_interface_version__, register_converters
from markitdown_paperlm._pdf_converter import PaperLMPdfConverter


def _paperlm_entry_point_installed() -> bool:
    """True if this package is importable via entry_points (i.e. pip-installed)."""
    try:
        eps = entry_points(group="markitdown.plugin")
    except TypeError:  # pragma: no cover — old importlib API
        return False
    return any(ep.name == "paperlm" for ep in eps)


def test_plugin_interface_version_is_1() -> None:
    assert __plugin_interface_version__ == 1


def test_register_converters_adds_paperlm_pdf_converter() -> None:
    md = MarkItDown()
    before = list(md._converters)  # access internal list (test-only)

    register_converters(md)

    after = list(md._converters)
    added = [c for c in after if c not in before]

    assert len(added) >= 1
    assert any(
        isinstance(entry.converter, PaperLMPdfConverter) for entry in added
    ), "PaperLMPdfConverter should be registered"
    paperlm = next(
        entry.converter for entry in added if isinstance(entry.converter, PaperLMPdfConverter)
    )
    assert paperlm.enable_formula is False


def test_register_converters_accepts_kwargs() -> None:
    md = MarkItDown()
    # Should not raise even with custom kwargs
    register_converters(
        md,
        paperlm_engine="auto",
        paperlm_enable_ocr=False,
        paperlm_enable_formula=True,
        unrelated_kwarg="ignored",
    )


def test_converter_defaults_keep_formula_enrichment_opt_in() -> None:
    converter = PaperLMPdfConverter()

    assert converter.enable_formula is False


@pytest.mark.skipif(
    not _paperlm_entry_point_installed(),
    reason=(
        "paperlm entry_point not registered — run `pip install -e .` to enable "
        "this end-to-end test. Pure source-tree pytest cannot discover plugins "
        "via entry_points."
    ),
)
def test_enable_plugins_true_loads_paperlm_via_entry_point() -> None:
    md = MarkItDown(enable_plugins=True)
    assert md._plugins_enabled is True
    assert any(
        isinstance(entry.converter, PaperLMPdfConverter) for entry in md._converters
    )
