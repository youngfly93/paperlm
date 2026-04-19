"""IR → Markdown serializer.

Deliberately simple in Week 1 — Week 3 adds inline formula detection,
caption linking, cross-page table merging, and reading-order repair.
"""

from __future__ import annotations

from markitdown_paperlm.ir import IR, Block, BlockType


class MarkdownSerializer:
    """Render an IR into a Markdown string."""

    def render(self, ir: IR) -> str:
        blocks = sorted(ir.blocks, key=lambda b: b.reading_order)
        lines: list[str] = []
        for block in blocks:
            chunk = self._render_block(block)
            if chunk:
                lines.append(chunk)
        md = "\n\n".join(lines).strip()
        return md + "\n" if md else ""

    def _render_block(self, block: Block) -> str:
        bt = block.type
        content = block.content

        if bt == BlockType.TITLE:
            return f"# {content}" if content else ""

        if bt == BlockType.HEADING:
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
            # Placeholder — Week 3 will render with image path + caption linking
            return "![](figure)"

        if bt == BlockType.TABLE:
            return content  # Already GFM-rendered by DoclingAdapter

        if bt == BlockType.FORMULA:
            inline = bool(block.attrs.get("inline", False))
            # Formula enrichment may be disabled → content empty but region
            # was detected. Emit a placeholder so the layout isn't lost.
            body = content if content else "[formula]"
            if inline:
                return f"${body}$"
            return f"$$\n{body}\n$$"

        if bt == BlockType.CODE:
            lang = block.attrs.get("language", "") or ""
            return f"```{lang}\n{content}\n```"

        if bt == BlockType.FOOTNOTE:
            return f"> {content}"

        return content
