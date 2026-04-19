"""Intermediate representation (IR) for scientific documents.

Designed so downstream serializers, processors, and bio-extensions
can consume structured blocks rather than raw Markdown strings.

**Stability note**: This IR is attached to DocumentConverterResult
as a non-standard attribute (`result.ir`). It is NOT part of the
MarkItDown public API. Python API consumers may use it; CLI and MCP
consumers will only see the rendered Markdown.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BlockType(str, Enum):
    """Semantic type of a document block."""

    TITLE = "title"
    HEADING = "heading"  # has attrs["level"]: int
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"  # has attrs["ordered"]: bool
    TABLE = "table"  # has attrs["rows"]: list[list[str]]
    FIGURE = "figure"  # has attrs["image_path"]: str | None
    CAPTION = "caption"  # has attrs["target_id"]: str (linked figure/table)
    FORMULA = "formula"  # has attrs["inline"]: bool, content is LaTeX
    CODE = "code"  # has attrs["language"]: str | None
    FOOTNOTE = "footnote"


@dataclass
class BBox:
    """Bounding box on a specific page."""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Block:
    """A semantic unit in a document.

    For TABLE: content is Markdown representation, attrs['rows'] holds raw 2D data.
    For FORMULA: content is LaTeX (without $ delimiters), attrs['inline'] tells serializer.
    For HEADING: content is heading text, attrs['level'] is 1-6.
    """

    type: BlockType
    content: str
    bbox: BBox | None = None
    reading_order: int = 0
    attrs: dict = field(default_factory=dict)


@dataclass
class IR:
    """Structured representation of a parsed document."""

    blocks: list[Block] = field(default_factory=list)
    engine_used: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.blocks)
