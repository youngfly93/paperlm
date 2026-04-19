"""Tests for JSON sidecar serialization."""

from __future__ import annotations

import io
import json
from typing import Any

from markitdown import StreamInfo
from pytest import MonkeyPatch

import markitdown_paperlm._pdf_converter as pdf_converter_mod
from markitdown_paperlm._pdf_converter import PaperLMPdfConverter
from markitdown_paperlm.ir import IR, BBox, Block, BlockType
from markitdown_paperlm.serializers.json_sidecar import (
    ir_to_chunks_jsonl,
    ir_to_dict,
    ir_to_json,
)


def _sample_ir() -> IR:
    return IR(
        engine_used="docling",
        warnings=["formula enrichment disabled"],
        metadata={"source": "unit-test", "ocr": {"mean_confidence": 0.92}},
        blocks=[
            Block(
                type=BlockType.TITLE,
                content="Paper Title",
                bbox=BBox(page=1, x0=10, y0=20, x1=200, y1=40),
                reading_order=0,
                attrs={"normalized_front_title": True},
            ),
            Block(
                type=BlockType.HEADING,
                content="Introduction",
                bbox=BBox(page=1, x0=10, y0=50, x1=200, y1=70),
                reading_order=1,
                attrs={"level": 2},
            ),
            Block(
                type=BlockType.FIGURE,
                content="",
                bbox=BBox(page=1, x0=10, y0=80, x1=200, y1=160),
                reading_order=2,
                attrs={"image_path": None},
            ),
        ],
    )


def test_ir_to_dict_contains_blocks_bbox_and_attrs() -> None:
    data = ir_to_dict(_sample_ir())

    assert data["schema_version"] == 1
    assert data["engine_used"] == "docling"
    assert data["warnings"] == ["formula enrichment disabled"]
    assert data["metadata"]["ocr"]["mean_confidence"] == 0.92
    assert data["block_count"] == 3
    assert data["blocks"][0]["type"] == "title"
    assert data["blocks"][0]["bbox"]["page"] == 1
    assert data["blocks"][0]["attrs"]["normalized_front_title"] is True


def test_ir_to_json_round_trips() -> None:
    data = json.loads(ir_to_json(_sample_ir()))

    assert data["blocks"][1]["content"] == "Introduction"
    assert data["blocks"][1]["attrs"]["level"] == 2


def test_ir_to_chunks_jsonl_skips_empty_visual_blocks() -> None:
    lines = ir_to_chunks_jsonl(_sample_ir()).splitlines()
    rows = [json.loads(line) for line in lines]

    assert [row["text"] for row in rows] == ["Paper Title", "Introduction"]
    assert rows[1]["level"] == 2


def test_pdf_converter_attaches_json_sidecars() -> None:
    class _Router:
        def convert(self, _stream):
            return _sample_ir()

    converter = PaperLMPdfConverter()
    converter._router = _Router()  # type: ignore[assignment]

    result = converter.convert(
        io.BytesIO(b"%PDF-1.4\n"),
        StreamInfo(mimetype="application/pdf", extension=".pdf"),
    )

    assert result.markdown.startswith("# Paper Title")
    assert result.paperlm_dict["block_count"] == 3
    assert json.loads(result.paperlm_json)["engine_used"] == "docling"
    assert "Paper Title" in result.paperlm_chunks_jsonl


def test_pdf_converter_generates_sidecars_lazily(monkeypatch: MonkeyPatch) -> None:
    class _Router:
        def convert(self, _stream):
            return _sample_ir()

    calls = {"dict": 0, "json": 0, "chunks": 0}

    def fake_ir_to_dict(ir: IR) -> dict[str, Any]:
        calls["dict"] += 1
        return {"block_count": len(ir.blocks)}

    def fake_ir_to_json(ir: IR) -> str:
        calls["json"] += 1
        return json.dumps({"engine_used": ir.engine_used})

    def fake_ir_to_chunks_jsonl(ir: IR) -> str:
        calls["chunks"] += 1
        return "\n".join(block.content for block in ir.blocks if block.content) + "\n"

    monkeypatch.setattr(pdf_converter_mod, "ir_to_dict", fake_ir_to_dict)
    monkeypatch.setattr(pdf_converter_mod, "ir_to_json", fake_ir_to_json)
    monkeypatch.setattr(pdf_converter_mod, "ir_to_chunks_jsonl", fake_ir_to_chunks_jsonl)

    converter = PaperLMPdfConverter()
    converter._router = _Router()  # type: ignore[assignment]

    result = converter.convert(
        io.BytesIO(b"%PDF-1.4\n"),
        StreamInfo(mimetype="application/pdf", extension=".pdf"),
    )

    assert result.markdown.startswith("# Paper Title")
    assert calls == {"dict": 0, "json": 0, "chunks": 0}

    assert result.paperlm_dict["block_count"] == 3
    assert result.paperlm_dict["block_count"] == 3
    assert calls["dict"] == 1

    assert json.loads(result.paperlm_json)["engine_used"] == "docling"
    assert json.loads(result.paperlm_json)["engine_used"] == "docling"
    assert calls["json"] == 1

    assert "Paper Title" in result.paperlm_chunks_jsonl
    assert "Paper Title" in result.paperlm_chunks_jsonl
    assert calls["chunks"] == 1
