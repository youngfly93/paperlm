"""IR → Markdown serializer.

Deliberately simple in Week 1 — Week 3 adds inline formula detection,
caption linking, cross-page table merging, and reading-order repair.
"""

from __future__ import annotations

import re

from markitdown_paperlm.ir import IR, Block, BlockType
from markitdown_paperlm.serializers.text_normalize import (
    clean_markdown_alt_text,
    clean_markdown_text,
)

_NUMERIC_HEADING_RE = re.compile(r"\d+(?:\.\d+)*\.?")


class MarkdownSerializer:
    """Render an IR into a Markdown string."""

    def render(self, ir: IR) -> str:
        blocks = sorted(ir.blocks, key=lambda b: b.reading_order)
        captions_by_order = {
            block.reading_order: block
            for block in blocks
            if block.type == BlockType.CAPTION
        }
        lines: list[str] = []
        for block in blocks:
            if (
                block.type == BlockType.CAPTION
                and block.attrs.get("target_type") == BlockType.FIGURE.value
            ):
                continue
            chunk = self._render_block(block, captions_by_order=captions_by_order)
            if chunk:
                lines.append(chunk)
        md = "\n\n".join(lines).strip()
        return md + "\n" if md else ""

    def _render_block(
        self,
        block: Block,
        *,
        captions_by_order: dict[int, Block] | None = None,
    ) -> str:
        bt = block.type
        content = clean_markdown_text(block.content)

        if bt == BlockType.TITLE:
            return f"# {content}" if content else ""

        if bt == BlockType.HEADING:
            if _is_spurious_short_heading(content):
                return content
            level = int(block.attrs.get("level", 2))
            level = max(1, min(6, level))
            return f"{'#' * level} {content}" if content else ""

        if bt == BlockType.PARAGRAPH:
            return content

        if bt == BlockType.LIST_ITEM:
            ordered = block.attrs.get("ordered", False)
            prefix = "1." if ordered else "-"
            return f"{prefix} {content}"

        if bt == BlockType.CAPTION:
            return f"*{content}*" if content else ""

        if bt == BlockType.FIGURE:
            image_path = block.attrs.get("image_path") or "figure"
            caption = _linked_caption_text(block, captions_by_order or {})
            return f"![{caption}]({image_path})"

        if bt == BlockType.TABLE:
            return content  # Already GFM-rendered by DoclingAdapter

        if bt == BlockType.FORMULA:
            inline = bool(block.attrs.get("inline", False))
            # Formula enrichment may be disabled → content empty but region
            # was detected. Emit a placeholder so the layout isn't lost.
            body = clean_markdown_text(block.content, normalize_words=False) or "[formula]"
            if inline:
                return f"${body}$"
            return f"$$\n{body}\n$$"

        if bt == BlockType.CODE:
            lang = block.attrs.get("language", "") or ""
            body = clean_markdown_text(block.content, normalize_words=False)
            return f"```{lang}\n{body}\n```"

        if bt == BlockType.FOOTNOTE:
            return f"> {content}"

        return content


def _linked_caption_text(
    block: Block,
    captions_by_order: dict[int, Block],
) -> str:
    cap_order = block.attrs.get("caption_reading_order")
    caption = captions_by_order.get(cap_order) if isinstance(cap_order, int) else None
    if caption is None or not caption.content:
        return ""
    return clean_markdown_alt_text(caption.content)


def _is_spurious_short_heading(content: str) -> bool:
    stripped = content.strip()
    if len(stripped) >= 3:
        return False
    if not stripped:
        return False
    return not bool(_NUMERIC_HEADING_RE.fullmatch(stripped))
