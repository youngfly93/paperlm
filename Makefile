.PHONY: help clean clean-check test test-fast test-all fresh-clone-test \
        benchmark-compare benchmark-compare-full benchmark-quality benchmark-ocr-confidence \
        benchmark-long-perf benchmark-long-profile benchmark-worker-pool \
        build check-twine-creds check-confirm-publish publish-test publish release-check

# Keep .pyc junk out of the source tree — both by disabling bytecode writing
# entirely and by redirecting any .pyc Python *does* still emit to a
# centralised cache directory. These are inherited by every recipe below.
export PYTHONDONTWRITEBYTECODE := 1
export PYTHONPYCACHEPREFIX := $(HOME)/.cache/paperlm-pycache

help:
	@echo "Local dev"
	@echo "  make clean            # remove ._*, __pycache__, .pyc, .pytest_cache"
	@echo "  make clean-check      # exit 1 if any junk files are committed"
	@echo "  make test-fast        # run unit tests that don't load ML models"
	@echo "  make test-all         # run everything (slow; Docling + PaddleOCR)"
	@echo "  make fresh-clone-test # reproduce fresh-clone install scenario"
	@echo "  make benchmark-compare # generate smoke competitor report (safe default)"
	@echo "  make benchmark-compare-full # opt-in full/heavy competitor report"
	@echo "  make benchmark-quality # generate snippet recall + reading-order report"
	@echo "  make benchmark-ocr-confidence # generate lightweight scanned OCR confidence report"
	@echo "  make benchmark-long-perf # profile one long PDF without full competitor matrix"
	@echo "  make benchmark-long-profile # cProfile paperlm breakdown on one long PDF"
	@echo "  make benchmark-worker-pool # compare fresh workers vs one pooled worker"
	@echo ""
	@echo "Release (see docs/RELEASE.md)"
	@echo "  make release-check    # full pre-flight: lint + types + tests + build"
	@echo "  make build            # build sdist + wheel into dist/"
	@echo "  make publish-test     # upload to TestPyPI (needs TWINE_* envvars)"
	@echo "  make publish          # upload to real PyPI (needs TWINE_* envvars)"

clean:
	@bash scripts/clean.sh

clean-check:
	@bash scripts/clean.sh --check

test-fast: clean
	pytest \
	  --ignore=tests/test_docling_adapter.py \
	  --ignore=tests/test_ocr_adapter.py \
	  --ignore=tests/test_pdf_converter_e2e.py

test-all: clean
	pytest tests/

fresh-clone-test: clean
	@echo "Building ephemeral venv to reproduce a first-time user's experience..."
	@bash -c 'set -e; \
	  TMPDIR=$$(mktemp -d); \
	  uv venv --python 3.12 $$TMPDIR/venv >/dev/null 2>&1; \
	  . $$TMPDIR/venv/bin/activate; \
	  export UV_LINK_MODE=copy; \
	  uv pip install -q -e ../markitdown/packages/markitdown pdfminer.six pdfplumber pytest; \
		  python -m pytest \
		    --ignore=tests/test_docling_adapter.py \
		    --ignore=tests/test_ocr_adapter.py \
		    --ignore=tests/test_pdf_converter_e2e.py; \
		  rm -rf $$TMPDIR'

benchmark-compare: clean
	python benchmarks/phase5_competitor_compare.py \
	  --profile smoke \
	  --tools markitdown_baseline,paperlm_plugin,docling_standalone \
	  --timeout-s 240 \
	  --max-rss-mb 4096 \
	  --max-rss-mb-hard 6144

benchmark-compare-full: clean
	python benchmarks/phase5_competitor_compare.py \
	  --profile full \
	  --tools markitdown_baseline,paperlm_plugin,docling_standalone,marker_cli,mineru_cli \
	  --timeout-s 900 \
	  --max-rss-mb 8192 \
	  --max-rss-mb-hard 8192

benchmark-quality: clean
	python benchmarks/phase6_quality_probe.py \
	  --timeout-s 240 \
	  --max-rss-mb-hard 6144

benchmark-ocr-confidence: clean
	python benchmarks/phase7_ocr_confidence_probe.py \
	  --timeout-s 240 \
	  --max-rss-mb-hard 4096

benchmark-long-perf: clean
	python benchmarks/phase8_long_pdf_perf_probe.py \
	  --fixture sample_arxiv_math.pdf \
	  --timeout-s 600 \
	  --max-rss-mb-hard 6144

benchmark-long-profile: clean
	python benchmarks/phase8_long_pdf_perf_probe.py \
	  --fixture sample_arxiv_math.pdf \
	  --tools paperlm_breakdown \
	  --profile-cpu \
	  --profile-top-n 30 \
	  --timeout-s 900 \
	  --max-rss-mb-hard 6144

benchmark-worker-pool: clean
	python benchmarks/phase9_worker_pool_probe.py \
	  --timeout-s 900 \
	  --max-rss-mb-hard 6144

# ---- release pipeline ---------------------------------------------------
#
# Pre-flight: everything that must be green before we are willing to publish.
# Exits non-zero the moment any gate fails.
release-check: clean clean-check
	ruff check src/ tests/
	uv run --no-project --with mypy mypy src/markitdown_paperlm src/paperlm
	pytest \
	  --ignore=tests/test_docling_adapter.py \
	  --ignore=tests/test_ocr_adapter.py \
	  --ignore=tests/test_pdf_converter_e2e.py \
	  --cov=markitdown_paperlm \
	  --cov-fail-under=60
	$(MAKE) build
	uv run --no-project --with twine twine check dist/*
	@echo ""
	@echo "release-check: all gates GREEN — ready to publish."

build: clean
	@python -c "import build" 2>/dev/null || pip install build
	rm -rf dist/
	python -m build

check-twine-creds:
	@test -n "$${TWINE_USERNAME}" || (echo "TWINE_USERNAME is required. Use: export TWINE_USERNAME=__token__" >&2; exit 1)
	@test -n "$${TWINE_PASSWORD}" || (echo "TWINE_PASSWORD is required. Use a TestPyPI/PyPI API token." >&2; exit 1)

check-confirm-publish:
	@if [ "$${CONFIRM_PUBLISH}" != "yes" ]; then \
	  echo ""; \
	  echo "Real PyPI upload is final — versions cannot be deleted."; \
	  echo "Re-run with: CONFIRM_PUBLISH=yes make publish"; \
	  exit 1; \
	fi

# TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-... expected via environment.
publish-test: check-twine-creds build
	uv run --no-project --with twine twine upload --non-interactive --repository testpypi dist/*

publish: check-twine-creds check-confirm-publish build
	uv run --no-project --with twine twine upload --non-interactive dist/*
