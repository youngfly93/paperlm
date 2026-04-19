#!/usr/bin/env bash
# Remove regenerable junk from the working tree.
#
# Needed frequently when src lives on exFAT (KINGSTON drive): macOS writes
# AppleDouble (._*) forks on every file write, and pytest / Python write
# __pycache__ / .pyc. None of these should end up in commits or archives,
# but they do appear in local `find` output.
#
# Usage:
#   ./scripts/clean.sh          # clean
#   ./scripts/clean.sh --check  # exit 1 if junk remains (useful in CI)

set -euo pipefail

PATTERNS=(
  "._*"
  ".___*"
  "__pycache__"
  "*.pyc"
  ".pytest_cache"
  ".ruff_cache"
  ".mypy_cache"
  "*.egg-info"
  ".DS_Store"
)

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

find_expr=()
for i in "${!PATTERNS[@]}"; do
  if [[ $i -gt 0 ]]; then find_expr+=("-o"); fi
  find_expr+=("-name" "${PATTERNS[$i]}")
done

if [[ "${1:-}" == "--check" ]]; then
  # We care that *committed* files don't include regenerable junk —
  # not that the working tree is free of it (pytest legitimately creates
  # __pycache__). When we're inside a git repo, grep `git ls-files`.
  # When we're not (e.g. a downloaded tarball), fall back to scanning
  # the working tree, which is still a useful sanity check.
  if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    committed=$(
      git -C "$REPO_ROOT" ls-files | \
        grep -E '(^|/)(\._|\.___|__pycache__|\.pytest_cache|\.ruff_cache|\.mypy_cache|\.DS_Store)' || true
      git -C "$REPO_ROOT" ls-files | grep -E '\.pyc$' || true
      git -C "$REPO_ROOT" ls-files | grep -E '\.egg-info' || true
    )
    if [[ -n "$committed" ]]; then
      echo "Regenerable junk has been committed — remove before pushing:"
      echo "$committed"
      exit 1
    fi
    echo "Clean (git-tracked files have no junk)."
    exit 0
  fi

  hits=$(find "$REPO_ROOT" \( "${find_expr[@]}" \) -not -path "*/.git/*" -not -path "*/.venv/*" 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$hits" -gt 0 ]]; then
    echo "Found $hits junk paths — run scripts/clean.sh"
    find "$REPO_ROOT" \( "${find_expr[@]}" \) -not -path "*/.git/*" -not -path "*/.venv/*" 2>/dev/null | head -20
    exit 1
  fi
  echo "Clean."
  exit 0
fi

removed=$(find "$REPO_ROOT" \( "${find_expr[@]}" \) -not -path "*/.git/*" -not -path "*/.venv/*" 2>/dev/null | wc -l | tr -d ' ')
find "$REPO_ROOT" \( "${find_expr[@]}" \) -not -path "*/.git/*" -not -path "*/.venv/*" -prune -exec rm -rf {} + 2>/dev/null || true
echo "Removed $removed junk paths."
