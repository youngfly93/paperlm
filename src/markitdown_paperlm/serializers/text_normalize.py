"""Text cleanup helpers applied at serialization boundaries."""

from __future__ import annotations

import re

_LIGATURE_CHARS = str.maketrans(
    {
        "\ufb00": "ff",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\ufb03": "ffi",
        "\ufb04": "ffl",
    }
)

_SPLIT_LIGATURE_RE = re.compile(
    r"(?P<left>[\w-])\s+(?P<lig>ffi|ffl|ff|fi|fl)\s+(?P<right>\w)",
    flags=re.IGNORECASE,
)

_DEHYPHEN_RE = re.compile(r"(?<=\w)-[ \t]*\r?\n[ \t]*(?=\w)")


def clean_markdown_text(text: str, *, normalize_words: bool = True) -> str:
    """Clean text so Markdown remains safe for text pipelines.

    The normal text path removes NUL bytes, normalizes Unicode ligature
    characters, fixes common split-ligature artifacts such as ``speci fi c``,
    and joins hard line-break hyphenations. Code/formula callers can disable
    word normalization while still removing NUL bytes.
    """
    if not text:
        return ""

    cleaned = text.replace("\x00", "")
    if not normalize_words:
        return cleaned

    cleaned = cleaned.translate(_LIGATURE_CHARS)
    cleaned = _DEHYPHEN_RE.sub("", cleaned)
    return _SPLIT_LIGATURE_RE.sub(
        lambda match: f"{match.group('left')}{match.group('lig')}{match.group('right')}",
        cleaned,
    )


def clean_markdown_alt_text(text: str) -> str:
    """Return a one-line Markdown image alt text."""
    cleaned = clean_markdown_text(text).replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.replace("[", "(").replace("]", ")")
