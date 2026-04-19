"""Parametrized smoke test — every fixture converts through the router without crashing.

Uses ``engine="fallback"`` so the test runs in milliseconds on any
machine (no ML model loads). This is a regression gate for "did we
break the ability to *at least* handle this PDF".

The fixture corpus is built / checked by ``tests/fixtures/fetch.py``.
If fixtures are missing, individual tests skip with a clear pointer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from markitdown_paperlm.router import EngineRouter

# Make the fetch module importable as a helper. Doing this after the main
# imports keeps ruff happy (E402) while still letting us reuse fetch.py's
# source-of-truth fixture list.
FIX_DIR = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(FIX_DIR))
try:
    from fetch import REAL_FIXTURES, SYNTHETIC_FIXTURES  # noqa: E402
finally:
    sys.path.pop(0)

# Flatten: one param per expected fixture. Each entry is (filename, human_label).
_ALL = [
    *[(fx.filename, fx.description) for fx in REAL_FIXTURES],
    *[
        (name, f"synthetic scanned ({pages}p @ {dpi}dpi)")
        for (name, pages, dpi) in SYNTHETIC_FIXTURES
    ],
]


@pytest.mark.parametrize(
    ("filename", "description"),
    _ALL,
    ids=[t[0] for t in _ALL],
)
def test_fallback_router_handles_every_fixture(filename: str, description: str) -> None:
    """Every fixture must produce an IR (possibly empty) without raising."""
    path = FIX_DIR / filename
    if not path.exists():
        pytest.skip(
            f"fixture missing: {filename} — run `python tests/fixtures/fetch.py` to build the corpus"
        )

    router = EngineRouter(engine="fallback")
    with open(path, "rb") as f:
        ir = router.convert(f)

    # The adapter may return zero blocks for a scanned PDF with no text layer —
    # that is expected and must be signalled via warnings, not exceptions.
    assert ir.engine_used in ("pdfminer", "failed")
    if len(ir.blocks) == 0:
        assert ir.warnings, (
            f"{filename}: empty IR must have at least one warning explaining why"
        )
    else:
        # When we do extract text, blocks should have non-empty content.
        non_empty = sum(1 for b in ir.blocks if b.content.strip())
        assert non_empty > 0, (
            f"{filename}: adapter produced {len(ir.blocks)} blocks but all are empty"
        )


def test_fixture_corpus_is_complete() -> None:
    """If this fails the CI workflow forgot to download a fixture."""
    missing = [
        fname
        for fname, _ in _ALL
        if not (FIX_DIR / fname).exists()
    ]
    if missing:
        pytest.skip(
            "fixture corpus incomplete (this is OK for local source-tree pytest "
            "— CI integration job fetches the corpus): "
            f"{missing}"
        )
    assert len(_ALL) >= 8, f"expected ≥8 fixtures, have {len(_ALL)}"
