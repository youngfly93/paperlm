"""Unit tests for EngineAdapter Protocol."""

import io

from markitdown_paperlm.engines.base import EngineAdapter
from markitdown_paperlm.ir import IR, Block, BlockType


class _StubEngine:
    """Minimal conforming implementation used to validate the Protocol."""

    name = "stub"

    def is_available(self) -> bool:
        return True

    def convert(self, pdf_stream: io.BytesIO) -> IR:
        return IR(
            blocks=[Block(type=BlockType.PARAGRAPH, content="stub")],
            engine_used=self.name,
        )


def test_protocol_runtime_check() -> None:
    stub = _StubEngine()
    assert isinstance(stub, EngineAdapter)


def test_stub_engine_produces_ir() -> None:
    stub = _StubEngine()
    ir = stub.convert(io.BytesIO(b""))
    assert len(ir.blocks) == 1
    assert ir.engine_used == "stub"
    assert ir.blocks[0].type == BlockType.PARAGRAPH
