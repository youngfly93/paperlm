# paperlm — Release Checklist

> Everything you need to do to ship **v0.1.0**. The current in-tree
> version is the final release candidate (`0.1.0`). Steps that require
> an account (GitHub / PyPI) are left for you to perform; all automatable
> parts are wired into `make` targets.

---

## 0. Preconditions

Before starting, make sure:

- [ ] `git` is configured with your name/email (`git config --global user.name`, `user.email`)
- [ ] You have a GitHub account and `gh` CLI authenticated (`gh auth status`)
- [ ] You have a PyPI account with 2FA enabled (https://pypi.org/manage/account/)
- [ ] You have a TestPyPI account (https://test.pypi.org/manage/account/)
- [ ] You've decided the **public repo URL** (update it everywhere it appears in README.md / pyproject.toml / this file)
- [x] **Version bump performed**. `src/markitdown_paperlm/__about__.py` is set to `0.1.0`:
      - Keep `0.1.0` for the real public release. This string is used by
        every tool: `pip install`, GitHub tag, release notes title.
      - If another TestPyPI rehearsal is needed before the real release,
        temporarily use `0.1.0a2`, `0.1.0a3`, … because every TestPyPI
        upload needs a new version.
- [ ] `rm -rf dist/` — old wheels will still carry the previous version.
      Every `make build` always produces the **current** `__about__.py`
      version, so clear old artefacts before publishing.

---

## 1. Pre-flight verification (`make release-check`)

Run the full verification suite locally. This mirrors what CI will do.

```bash
make release-check
```

Under the hood:

1. `scripts/clean.sh` removes AppleDouble/pycache junk
2. `ruff check src/ tests/` — lint
3. `mypy src/markitdown_paperlm src/paperlm` — type check
4. `pytest --cov=markitdown_paperlm --cov-fail-under=60` (fast suite)
5. `scripts/clean.sh --check` — no junk committed
6. Build sdist + wheel → `dist/`
7. `twine check dist/*` — metadata is well-formed

Every one of these must pass. If anything fails here, do **not** publish.

---

## 2. Git: create the public repository

```bash
cd /path/to/paperlm

# First commit (review the list before running)
git init
git add .
make clean-check          # must pass before commit
git commit -m "chore: initial public release v0.1.0"

# Push to GitHub
gh repo create paperlm --public --description \
  "Scientific PDFs -> Markdown. A MarkItDown plugin using Docling + PaddleOCR."
git branch -M main
git remote add origin git@github.com:youngfly93/paperlm.git
git push -u origin main
```

**Verify**:
- [ ] GitHub Actions kicks in and the `fast` + `fresh-clone` + `clean-check` jobs go green
- [ ] The `integration` job is available as a manual dispatch on the Actions tab

---

## 3. PyPI: test release to TestPyPI first

Status: completed for `paperlm==0.1.0a1` on TestPyPI.

Never publish directly to real PyPI on the first try. Use TestPyPI as a rehearsal.

```bash
# Get an API token: https://test.pypi.org/manage/account/token/
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-<your-test-token>

make publish-test
```

**Then verify in a clean venv**:

Verified for `paperlm==0.1.0a1`:

- `uv pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ 'paperlm[docling]'`
- `paperlm-batch --help`
- `markitdown --list-plugins` shows `paperlm`
- `paperlm-batch --engine fallback` converts `sample_arxiv_table_heavy.pdf`
- `paperlm-batch --engine docling` converts `sample_arxiv_table_heavy.pdf`

Observed clean-install smoke:

- fallback path: `status=ok`, `engine_used=pdfminer`, `chars=50681`
- Docling path: `status=ok`, `engine_used=docling`, `chars=54069`, first line
  `# TARGET: Benchmarking Table Retrieval for Generative Tasks`

```bash
TMPDIR=$(mktemp -d)
uv venv --python 3.12 $TMPDIR/v
source $TMPDIR/v/bin/activate
uv pip install --index-url https://test.pypi.org/simple/ \
               --extra-index-url https://pypi.org/simple/ \
               'paperlm[docling]'
markitdown --list-plugins      # must show `paperlm`
echo 'hello' > /tmp/dummy.txt   # sanity smoke
rm -rf $TMPDIR
```

If anything is off (missing deps, bad metadata, wrong Python version gates),
bump the version in `src/markitdown_paperlm/__about__.py` (e.g. `0.1.0a2`)
and re-publish to TestPyPI.

---

## 4. PyPI: real release

Status: completed for `paperlm==0.1.0` on PyPI.

Once TestPyPI dry-run is clean:

```bash
# Different token than test: https://pypi.org/manage/account/token/
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-<your-real-token>

make publish
```

**Verify**:

```bash
pip install paperlm[docling]
markitdown --list-plugins
```

Verified for `paperlm==0.1.0`:

- `uv pip install 'paperlm[docling]==0.1.0'`
- `import paperlm` reports `0.1.0`
- `paperlm-batch --help`
- `markitdown --list-plugins` shows `paperlm`
- fallback path: `status=ok`, `engine_used=pdfminer`, `chars=50681`
- Docling path: `status=ok`, `engine_used=docling`, `chars=54069`, first line
  `# TARGET: Benchmarking Table Retrieval for Generative Tasks`

---

## 5. GitHub Release

```bash
# Tag the commit that matches what's on PyPI
git tag -a v0.1.0 -m "v0.1.0 — first public release"
git push origin v0.1.0

gh release create v0.1.0 \
  --title "v0.1.0 — first public release" \
  --notes-file docs/release_notes/v0.1.0.md
```

Template for `docs/release_notes/v0.1.0.md` is below; adjust per reality.

```markdown
## Highlights

- MarkItDown plugin for PDF conversion using Docling 2.90 (MIT) + PaddleOCR mobile.
- 100% pass rate on 8 real-world fixtures spanning 1-86 pages, Chinese/English.
- Peak RSS ≤ 4 GB on every fixture (see benchmarks/phase4_integration.md).
- `paperlm_engine="auto"` routes scanned PDFs to PaddleOCR; text-layer PDFs to Docling.
- Apache-2.0. No GPL/AGPL is transitively pulled unless you opt in to `[marker]` / `[mineru]`.

## Install

    pip install paperlm[docling]            # default recommendation
    pip install paperlm[docling,ocr]        # + local OCR for scanned PDFs

## Known limits

See README "Known limits" section and benchmarks/phase4_integration.md.
```

---

## 6. Community pings

Do these **the same day** you push the release tag. Use the existing-work
links from this repo as evidence — the benchmarks and README already have
everything needed.

### Must-do

- [ ] MarkItDown: open an issue at https://github.com/microsoft/markitdown/issues
      titled **"[plugin] paperlm — improved PDF converter
      (Docling + PaddleOCR)"**. Link to `README.md`, mention the table-heavy
      before/after as the most convincing example. Ask if they want it added
      to a recommended-plugins list.

- [ ] Docling: open a discussion at https://github.com/docling-project/docling/discussions
      showing this is a downstream use-case. Post the phase4 integration numbers.

### Should-do (higher signal, low effort)

- [ ] Tweet / X post with the table-heavy before/after screenshot
- [ ] Show HN post, title: **"Show HN: paperlm — a scientific-paper PDF to Markdown plugin for MarkItDown"**
- [ ] Reddit r/LocalLLaMA post with the RSS fix benchmark
- [ ] v2ex (中文) or 少数派 tech post using `README_zh.md` as the body

### Optional

- [ ] PR to https://github.com/ to add this repo to any `awesome-*` lists:
      `awesome-scientific-computing`, `awesome-llm-tools`, `awesome-rag`.

---

## 7. Post-release monitoring (first 72 h)

- [ ] Watch GitHub issues/notifications closely
- [ ] Any bug report: triage within 24 h — either fix & publish `0.1.1`, or acknowledge with a workaround
- [ ] Add a `0.1.x` branch if someone needs a non-breaking fix

---

## Appendix A — Version bump

All version numbers live in exactly one place:

```python
# src/markitdown_paperlm/__about__.py
__version__ = "0.1.0"
```

Bump rules:
- **patch** (0.1.1): bug fix only, no new features
- **minor** (0.2.0): new feature, new kwarg, new engine — backwards compatible
- **major** (1.0.0): API break OR PaperLM independent fork

---

## Appendix B — Rollback

If a release is critically broken:

```bash
# PyPI does NOT allow deletion of a published version number.
# Instead, yank it so pip won't install it by default:
pip install twine
# go to https://pypi.org/manage/project/paperlm/releases/
# and click "Options → Yank this release" for the broken version.

# Then immediately publish a fixed version (e.g. 0.1.0 → 0.1.1).
```

---

## Appendix C — If a reviewer says something is broken

- [ ] Reproduce in a fresh venv (`make fresh-clone-test`)
- [ ] Reproduce in a full-install venv (`make test-fast`)
- [ ] If the reviewer used a command, copy it verbatim. Most of our past
      "failures" were actually environment mismatches, not code bugs.
