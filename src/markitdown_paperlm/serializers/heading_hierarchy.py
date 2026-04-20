"""Heading hierarchy repair and journal-furniture normalization.

Docling can emit late-stage main section headings after the first few
subsection headings in two-column journal layouts. The most visible case is
Nature-style PDFs where ``## Methods`` appears after method subsections such
as ``## Plant growth conditions``. This module applies conservative IR-level
repairs before Markdown/JSON serialization.
"""

from __future__ import annotations

import re

from markitdown_paperlm.ir import Block, BlockType

_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_FIGURE_HEADING_KEY_RE = re.compile(r"^(?:fig|figure) \d+\b")

_MAIN_SECTION_KEYS = {
    "abstract",
    "introduction",
    "results",
    "discussion",
    "conclusions",
    "methods",
    "materials and methods",
    "limitations",
    "references",
    "references and notes",
    "data availability",
    "code availability",
    "reporting summary",
    "acknowledgments",
    "acknowledgements",
    "author contributions",
    "competing interests",
    "additional information",
    "supplementary materials",
}

_METHODS_KEYS = {"methods", "materials and methods"}

_CANONICAL_HEADINGS = {
    "acknowledgements": "Acknowledgements",
    "acknowledgments": "Acknowledgements",
    "additional information": "Additional Information",
    "article": "Article",
    "author contributions": "Author Contributions",
    "code availability": "Code Availability",
    "competing interests": "Competing Interests",
    "data availability": "Data Availability",
    "materials and methods": "Materials and Methods",
    "microbial ecology": "Microbial Ecology",
    "nature ecology evolution": "Nature Ecology & Evolution",
    "references and notes": "References and Notes",
    "reprints and permissions information is available at": (
        "Reprints and permissions information is available at"
    ),
    "research article": "Research Article",
    "reporting summary": "Reporting Summary",
    "supplementary materials": "Supplementary Materials",
    "view article online": "View Article Online",
    "view the article online": "View the Article Online",
}

_JOURNAL_FURNITURE_KEYS = {
    "article",
    "editor s summary",
    "microbial ecology",
    "nature ecology evolution",
    "reprints and permissions information is available at",
    "research article",
    "view article online",
    "view the article online",
}

_METHOD_SUBHEADING_TERMS = {
    "16s",
    "analysis",
    "assay",
    "bacterial",
    "carbon source",
    "cell",
    "collection",
    "community",
    "construction",
    "culture",
    "data analysis",
    "dna",
    "enrichment",
    "experiment",
    "experimental",
    "extraction",
    "genome",
    "greenhouse",
    "growth",
    "hplc",
    "infection",
    "inoculation",
    "in vitro",
    "isolation",
    "metabolomic",
    "metagenomic",
    "microbiome",
    "model",
    "models",
    "plant",
    "profiling",
    "quantifying",
    "reconstruction",
    "sample",
    "sequencing",
    "simulated",
    "statistical",
    "strain",
    "strains",
    "synthetic community",
    "validation",
    "whole genome",
}

_MAX_BACKSCAN_BLOCKS = 90


def normalize_and_repair_headings(blocks: list[Block]) -> list[Block]:
    """Return blocks with cleaner heading text and repaired main sections."""
    if not blocks:
        return blocks

    out = list(blocks)
    _normalize_heading_text(out)
    out = _repair_methods_heading_order(out)
    _restamp(out)
    return out


def _normalize_heading_text(blocks: list[Block]) -> None:
    title_key = _first_title_key(blocks)

    for block in blocks:
        if block.type != BlockType.HEADING:
            continue
        key = _heading_key(block.content)
        if not key:
            continue

        if title_key and key == title_key:
            _demote_heading(block, reason="duplicate_title")
            continue

        if key in _JOURNAL_FURNITURE_KEYS:
            _demote_heading(block, reason="journal_furniture")
            block.content = _CANONICAL_HEADINGS.get(key, _title_like(block.content))
            continue

        if _FIGURE_HEADING_KEY_RE.match(key):
            _demote_heading(block, reason="figure_caption_heading")
            continue

        canonical = _CANONICAL_HEADINGS.get(key)
        if canonical:
            block.content = canonical


def _repair_methods_heading_order(blocks: list[Block]) -> list[Block]:
    out = list(blocks)
    index = 0
    while index < len(out):
        block = out[index]
        if block.type == BlockType.HEADING and _heading_key(block.content) in _METHODS_KEYS:
            insert_at = _methods_insert_index(out, index)
            if insert_at < index:
                methods = out.pop(index)
                out.insert(insert_at, methods)
                index = insert_at + 1
                continue
        index += 1
    return out


def _methods_insert_index(blocks: list[Block], methods_index: int) -> int:
    boundary = _previous_main_boundary(blocks, methods_index)
    scan_start = max(boundary + 1, methods_index - _MAX_BACKSCAN_BLOCKS)
    insert_at = methods_index

    for idx in range(methods_index - 1, scan_start - 1, -1):
        block = blocks[idx]
        if block.type != BlockType.HEADING:
            continue
        key = _heading_key(block.content)
        if key in _MAIN_SECTION_KEYS:
            break
        if _looks_like_method_subheading(block.content):
            insert_at = idx

    return insert_at


def _previous_main_boundary(blocks: list[Block], before_index: int) -> int:
    for idx in range(before_index - 1, -1, -1):
        block = blocks[idx]
        if block.type == BlockType.TITLE:
            return idx
        if block.type == BlockType.HEADING and _heading_key(block.content) in _MAIN_SECTION_KEYS:
            return idx
    return -1


def _looks_like_method_subheading(text: str) -> bool:
    key = _heading_key(text)
    if not key or key in _MAIN_SECTION_KEYS:
        return False
    return any(term in key for term in _METHOD_SUBHEADING_TERMS)


def _first_title_key(blocks: list[Block]) -> str:
    for block in blocks:
        if block.type == BlockType.TITLE:
            return _heading_key(block.content)
    return ""


def _demote_heading(block: Block, *, reason: str) -> None:
    block.type = BlockType.PARAGRAPH
    block.attrs["demoted_heading_reason"] = reason


def _title_like(text: str) -> str:
    words = _SPACE_RE.sub(" ", text.strip()).split(" ")
    return " ".join(word.capitalize() if not word.isupper() else word for word in words)


def _heading_key(text: str) -> str:
    normalized = _NON_ALNUM_RE.sub(" ", text.lower())
    return _SPACE_RE.sub(" ", normalized).strip()


def _restamp(blocks: list[Block]) -> None:
    for idx, block in enumerate(blocks):
        block.reading_order = idx
