"""Front-matter normalization for scientific PDFs.

Docling usually emits high-quality blocks, but the first page can still
start with affiliation, email, journal, or preprint-watermark text after
two-column repair. For Markdown/RAG use, the document should start with
the paper title whenever a plausible title block is available.
"""

from __future__ import annotations

import re

from markitdown_paperlm.ir import Block, BlockType

_TEXTUAL_TYPES = {
    BlockType.TITLE,
    BlockType.HEADING,
    BlockType.PARAGRAPH,
}

_AFFILIATION_HINTS = (
    "@",
    "affiliation",
    "correspondence",
    "department",
    "ecole",
    "email",
    "genomique",
    "institute",
    "institut",
    "laboratory",
    "school of",
    "university",
)

_NOISE_PREFIXES = (
    "abstract:",
    "article",
    "bioRxiv preprint".lower(),
    "doi:",
    "keywords:",
    "vol.",
)


def normalize_front_matter(blocks: list[Block]) -> list[Block]:
    """Promote the most plausible first-page title to the start.

    The function is deliberately conservative:

    - Only the earliest bboxed page is touched.
    - Every block is preserved.
    - A block is promoted only if it looks title-like and not like an
      affiliation, DOI, abstract lead, or author-address line.
    - Obvious affiliation/noise blocks on the first page are moved after
      the first-page main content so they do not become the Markdown lead.
    """
    if not blocks:
        return blocks

    first_page = _first_bboxed_page(blocks)
    if first_page is None:
        return blocks

    first_indices = [
        i for i, block in enumerate(blocks) if block.bbox and block.bbox.page == first_page
    ]
    if len(first_indices) < 2:
        return blocks

    title_idx = _select_title_index(blocks, first_indices)
    if title_idx is None:
        return blocks

    title = blocks[title_idx]
    title.type = BlockType.TITLE
    title.attrs["normalized_front_title"] = True

    primary: list[Block] = []
    deprioritized: list[Block] = []
    first_index_set = set(first_indices)
    for idx in first_indices:
        if idx == title_idx:
            continue
        block = blocks[idx]
        if _is_front_matter_noise(block.content):
            deprioritized.append(block)
        else:
            primary.append(block)

    reordered: list[Block] = []
    for idx, block in enumerate(blocks):
        if idx == first_indices[0]:
            reordered.extend([title, *primary, *deprioritized])
        if idx in first_index_set:
            continue
        reordered.append(block)

    for order, block in enumerate(reordered):
        block.reading_order = order
    return reordered


def _first_bboxed_page(blocks: list[Block]) -> int | None:
    pages = [block.bbox.page for block in blocks if block.bbox is not None]
    return min(pages) if pages else None


def _select_title_index(blocks: list[Block], indices: list[int]) -> int | None:
    scored: list[tuple[int, int]] = []
    for idx in indices:
        block = blocks[idx]
        score = _title_score(block)
        if score > 0:
            scored.append((score, idx))
    if not scored:
        return None
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return scored[0][1]


def _title_score(block: Block) -> int:
    text = _clean(block.content)
    if not text or block.type not in _TEXTUAL_TYPES:
        return -100
    if not _looks_title_like(text):
        return -100
    if _is_not_title(text):
        return -100
    if _is_front_matter_noise(text):
        return -100

    score = 0
    if block.type == BlockType.TITLE:
        score += 100
    elif block.type == BlockType.HEADING:
        score += 70
    else:
        score += 25

    length = len(text)
    if 25 <= length <= 180:
        score += 20
    elif length > 220:
        score -= 25

    if ":" in text:
        score += 8
    if re.search(r"\b(survey|benchmark|analysis|model|models|database|bioinformatics)\b", text, re.I):
        score += 12
    return score


def _looks_title_like(text: str) -> bool:
    if len(text) < 8:
        return False
    if text[0] in ",.;:)]}":
        return False
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", text):
        return False
    if re.fullmatch(r"[\W\d_]+", text):
        return False
    return True


def _is_front_matter_noise(text: str) -> bool:
    clean = _clean(text)
    lower = clean.lower()
    if not clean:
        return False
    if clean.startswith(("Abstract:", "摘要", "关键词")):
        return False
    if clean[0] in ",.;:)]}":
        return True
    if lower.startswith(_NOISE_PREFIXES):
        return True
    if "doi.org" in lower or "copyright holder" in lower:
        return True
    if _looks_like_affiliation(clean):
        return True
    return False


def _is_not_title(text: str) -> bool:
    clean = _clean(text)
    lower = clean.lower()
    if lower.startswith(("abstract:", "keywords:", "doi:")):
        return True
    if clean.startswith(("摘要", "关键词")):
        return True
    return False


def _looks_like_affiliation(text: str) -> bool:
    lower = text.lower()
    if any(hint in lower for hint in _AFFILIATION_HINTS):
        return True
    if re.match(r"^\d+\s+[A-Z][\w-]+", text) and "," in text:
        return True
    if re.match(r"^[\u2660-\u2666\u2020\u2021*]", text):
        return True
    if len(re.findall(r"\b[A-Z][a-z]+ [A-Z][a-z]+", text)) >= 3:
        return True
    return False


def _clean(text: str) -> str:
    return " ".join(text.split())
