"""Tests for OCRAdapter — skipped if PaddleOCR not installed."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from markitdown_paperlm.engines.base import EngineAdapter
from markitdown_paperlm.engines.ocr_adapter import OCRAdapter
from markitdown_paperlm.ir import BlockType

pytestmark = pytest.mark.skipif(
    not OCRAdapter().is_available(),
    reason="paddleocr / paddle / pypdfium2 not installed (use pip install '.[ocr]')",
)

FIX = Path(__file__).parent / "fixtures"


def test_ocr_conforms_to_protocol() -> None:
    adapter = OCRAdapter()
    assert isinstance(adapter, EngineAdapter)
    assert adapter.name == "paddleocr"


def test_ocr_is_available_when_deps_present() -> None:
    assert OCRAdapter().is_available()


def test_ocr_empty_stream_does_not_crash() -> None:
    ir = OCRAdapter().convert(io.BytesIO(b""))
    assert ir.engine_used == "paddleocr"
    # bad bytes → warning, no blocks
    assert ir.warnings
    assert len(ir.blocks) == 0


def test_default_variant_is_mobile() -> None:
    """Week 4 Day 1 decision: default to the low-RSS mobile models.

    The server variant was dropped as default because it used ~4x the RSS
    for no measurable quality gain on our Chinese bioinformatics fixture.
    """
    a = OCRAdapter()
    assert a.variant == "mobile"
    assert a.low_memory is False
    assert a.render_dpi == 150


def test_invalid_variant_raises() -> None:
    with pytest.raises(ValueError):
        OCRAdapter(variant="nonsense")


def test_low_memory_sets_paddle_env_when_loading_ocr(monkeypatch) -> None:
    """Constructing with low_memory=True should publish paddle allocator flags.

    We stub out PaddleOCR so no models load, then inspect os.environ.
    """
    import os
    import sys
    import types

    # Avoid polluting the real env after the test.
    monkeypatch.delenv("FLAGS_allocator_strategy", raising=False)
    monkeypatch.delenv("FLAGS_fraction_of_cpu_memory_to_use", raising=False)

    fake_mod = types.ModuleType("paddleocr")

    class FakeOCR:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_mod.PaddleOCR = FakeOCR
    monkeypatch.setitem(sys.modules, "paddleocr", fake_mod)

    # Fresh cache so we go through the init path.
    OCRAdapter._ocr_cache = {}
    adapter = OCRAdapter(variant="mobile", low_memory=True)
    inst = adapter._get_ocr()

    assert isinstance(inst, FakeOCR)
    assert os.environ.get("FLAGS_allocator_strategy") == "naive_best_fit"
    assert "text_detection_model_name" in inst.kwargs
    assert inst.kwargs["text_detection_model_name"] == "PP-OCRv5_mobile_det"


@pytest.mark.skipif(
    not (FIX / "sample_scanned_1p.pdf").exists(), reason="fixture missing"
)
def test_ocr_on_scanned_chinese_pdf_1page() -> None:
    """The whole point: Docling OCR garbles Chinese; PaddleOCR must do better.

    Uses the 1-page fixture to keep CI fast (OCR is ~20s per page on CPU).
    """
    adapter = OCRAdapter(lang="ch")
    with open(FIX / "sample_scanned_1p.pdf", "rb") as f:
        ir = adapter.convert(f)

    assert ir.engine_used == "paddleocr"
    # Single page should still yield many text lines
    assert len(ir.blocks) > 10, f"expected >10 OCR blocks, got {len(ir.blocks)}"
    assert all(b.type == BlockType.PARAGRAPH for b in ir.blocks)

    all_text = "\n".join(b.content for b in ir.blocks)
    # Chinese title contains 生物信息学; issue header contains 生命科学 / 2024年11月
    assert "生物" in all_text or "生命" in all_text or "2024" in all_text, (
        f"Expected Chinese bioinformatics content; got first 400 chars: {all_text[:400]!r}"
    )

    # bbox and confidence should be populated
    with_bbox = [b for b in ir.blocks if b.bbox is not None]
    assert len(with_bbox) > 0
    with_conf = [b for b in ir.blocks if "ocr_confidence" in b.attrs]
    assert len(with_conf) == len(ir.blocks)
    ocr_meta = ir.metadata["ocr"]
    assert ocr_meta["pages"][0]["line_count"] > 0
    assert ocr_meta["mean_confidence"] is not None
    assert ocr_meta["empty_pages"] == []


def test_ocr_preserves_stream_position() -> None:
    stream = io.BytesIO(b"not a pdf")
    stream.read(3)
    before = stream.tell()
    OCRAdapter().convert(stream)
    assert stream.tell() == before
