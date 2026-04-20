"""JSON sidecar serializers for PaperLM IR."""

from __future__ import annotations

import json
from typing import Any

from markitdown_paperlm.ir import IR, BBox, Block, BlockType
from markitdown_paperlm.serializers.text_normalize import clean_markdown_text

IR_SCHEMA_VERSION = 1


def ir_to_dict(ir: IR) -> dict[str, Any]:
    """Return a JSON-serializable dictionary for the full IR."""
    return {
        "schema_version": IR_SCHEMA_VERSION,
        "engine_used": ir.engine_used,
        "warnings": list(ir.warnings),
        "metadata": _json_safe(ir.metadata),
        "block_count": len(ir.blocks),
        "blocks": [_block_to_dict(index, block) for index, block in enumerate(ir.blocks)],
    }


def ir_to_json(ir: IR, *, indent: int | None = 2) -> str:
    """Serialize the full IR as UTF-8 friendly JSON text."""
    return json.dumps(ir_to_dict(ir), ensure_ascii=False, indent=indent)


def ir_to_chunks_jsonl(ir: IR) -> str:
    """Serialize text-bearing blocks as one JSON object per line.

    This is intentionally simple: it gives RAG pipelines a stable, low-friction
    starting point without pretending to solve semantic chunking yet.
    """
    lines: list[str] = []
    for index, block in enumerate(ir.blocks):
        text = _clean_block_content(block).strip()
        if not text:
            continue
        row = {
            "block_index": index,
            "type": block.type.value,
            "page": block.bbox.page if block.bbox else None,
            "bbox": _bbox_to_dict(block.bbox),
            "text": text,
        }
        if block.type == "heading":
            row["level"] = block.attrs.get("level")
        lines.append(json.dumps(row, ensure_ascii=False))
    return "\n".join(lines) + ("\n" if lines else "")


def _block_to_dict(index: int, block: Block) -> dict[str, Any]:
    return {
        "index": index,
        "type": block.type.value,
        "content": _clean_block_content(block),
        "bbox": _bbox_to_dict(block.bbox),
        "reading_order": block.reading_order,
        "attrs": _json_safe(block.attrs),
    }


def _bbox_to_dict(bbox: BBox | None) -> dict[str, float | int] | None:
    if bbox is None:
        return None
    return {
        "page": bbox.page,
        "x0": bbox.x0,
        "y0": bbox.y0,
        "x1": bbox.x1,
        "y1": bbox.y1,
    }


def _clean_block_content(block: Block) -> str:
    return clean_markdown_text(
        block.content,
        normalize_words=block.type not in (BlockType.CODE, BlockType.FORMULA),
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return str(value)
