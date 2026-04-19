"""Tests for EngineRouter — degradation chain, forced engines, safety."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from markitdown_paperlm.engines.fallback_adapter import FallbackAdapter
from markitdown_paperlm.ir import IR, Block, BlockType
from markitdown_paperlm.router import VALID_ENGINES, EngineRouter

FIX = Path(__file__).parent / "fixtures"


# ---------- Stub adapters for deterministic chain testing ----------


class _GoodAdapter:
    name = "good"

    def is_available(self) -> bool:
        return True

    def convert(self, stream: io.BytesIO) -> IR:
        return IR(
            engine_used=self.name,
            blocks=[Block(type=BlockType.PARAGRAPH, content="good result")],
        )


class _EmptyAdapter:
    name = "empty"

    def is_available(self) -> bool:
        return True

    def convert(self, stream: io.BytesIO) -> IR:
        return IR(engine_used=self.name, warnings=["nothing found"])


class _RaisingAdapter:
    name = "raising"

    def is_available(self) -> bool:
        return True

    def convert(self, stream: io.BytesIO) -> IR:
        raise RuntimeError("boom")


class _UnavailableAdapter:
    name = "missing"

    def is_available(self) -> bool:
        return False

    def convert(self, stream: io.BytesIO) -> IR:  # pragma: no cover
        raise NotImplementedError


# ---------- Basic validation ----------


def test_invalid_engine_raises() -> None:
    with pytest.raises(ValueError):
        EngineRouter(engine="nonexistent")


def test_valid_engines_set() -> None:
    assert "auto" in VALID_ENGINES
    assert "docling" in VALID_ENGINES
    assert "ocr" in VALID_ENGINES
    assert "fallback" in VALID_ENGINES


def test_formula_enrichment_is_opt_in_by_default() -> None:
    assert EngineRouter().enable_formula is False


# ---------- Chain semantics (injected chains) ----------


def _route_with_chain(chain: list, pdf_bytes: bytes = b"") -> IR:
    r = EngineRouter(engine="fallback")
    # Override internal chain for deterministic test — we inject the adapters.
    # Accept **_ so the lambda matches the (is_scanned=...) kwarg the router passes.
    r._build_chain = lambda **_: chain  # type: ignore[method-assign]
    return r.convert(io.BytesIO(pdf_bytes))


def test_good_first_wins() -> None:
    ir = _route_with_chain([_GoodAdapter(), _EmptyAdapter()])
    assert ir.engine_used == "good"
    assert len(ir.blocks) == 1


def test_empty_result_tries_next() -> None:
    ir = _route_with_chain([_EmptyAdapter(), _GoodAdapter()])
    assert ir.engine_used == "good"
    # Previous adapter's warnings should be preserved as a trail
    assert any("empty" in w for w in ir.warnings)


def test_raising_adapter_continues_chain() -> None:
    ir = _route_with_chain([_RaisingAdapter(), _GoodAdapter()])
    assert ir.engine_used == "good"
    assert any("boom" in w for w in ir.warnings)


def test_unavailable_skipped() -> None:
    ir = _route_with_chain([_UnavailableAdapter(), _GoodAdapter()])
    assert ir.engine_used == "good"
    assert any("not available" in w.lower() for w in ir.warnings)


def test_all_fail_returns_failed_ir() -> None:
    ir = _route_with_chain([_RaisingAdapter(), _RaisingAdapter()])
    assert ir.engine_used == "failed"
    assert len(ir.blocks) == 0
    assert ir.warnings


def test_last_adapter_result_accepted_even_if_empty() -> None:
    """Last chain entry returns — even empty — so we always have a warnings trail."""
    ir = _route_with_chain([_EmptyAdapter()])
    assert ir.engine_used == "empty"
    assert ir.warnings


# ---------- Stream safety ----------


def test_router_preserves_stream_position() -> None:
    stream = io.BytesIO(b"\x00" * 100)
    stream.read(50)
    before = stream.tell()
    router = EngineRouter(engine="fallback")
    router.convert(stream)
    assert stream.tell() == before


# ---------- Real end-to-end with fallback engine ----------


@pytest.mark.skipif(
    not (FIX / "sample_en_two_col.pdf").exists(), reason="fixture missing"
)
@pytest.mark.skipif(
    __import__("importlib").util.find_spec("pdfminer") is None,
    reason="pdfminer.six is a core dep — install via `pip install -e .`",
)
def test_forced_fallback_produces_pdfminer_ir() -> None:
    router = EngineRouter(engine="fallback")
    with open(FIX / "sample_en_two_col.pdf", "rb") as f:
        ir = router.convert(f)
    assert ir.engine_used == "pdfminer"
    assert len(ir.blocks) > 0


def test_forced_fallback_default_chain_has_only_fallback() -> None:
    router = EngineRouter(engine="fallback")
    chain = router._build_chain()
    assert len(chain) == 1
    assert isinstance(chain[0], FallbackAdapter)


def test_auto_mode_scanned_prefers_ocr_over_docling() -> None:
    """Day-5 regression: on scanned input, OCR should come before Docling."""
    r = EngineRouter(engine="auto")
    chain_scanned = r._build_chain(is_scanned=True)
    chain_text = r._build_chain(is_scanned=False)

    # Both chains include FallbackAdapter at the end.
    assert isinstance(chain_scanned[-1], FallbackAdapter)
    assert isinstance(chain_text[-1], FallbackAdapter)

    # If OCR and Docling are both available, ordering must differ.
    names_scanned = [a.name for a in chain_scanned]
    names_text = [a.name for a in chain_text]
    if "paddleocr" in names_scanned and "docling" in names_scanned:
        assert names_scanned.index("paddleocr") < names_scanned.index("docling")
    if "docling" in names_text and "paddleocr" in names_text:
        assert names_text.index("docling") < names_text.index("paddleocr")
