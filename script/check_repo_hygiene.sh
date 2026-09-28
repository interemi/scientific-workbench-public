#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

fail() {
  echo "repo hygiene failed: $*" >&2
  exit 1
}

scope="${1:-filesystem}"
[[ "$#" -le 1 && ( "$scope" == filesystem || "$scope" == --git-visible ) ]] || fail "usage: check_repo_hygiene.sh [--git-visible]"

# Publication checks concern Git candidates; strict local gates retain their
# filesystem checks. Ignored Finder metadata is never deleted by either mode.
if [[ "$scope" == --git-visible ]]; then
  ds_store_files="$(git ls-files --cached --others --exclude-standard | grep -E '(^|/)\.DS_Store$' || true)"
else
  ds_store_files="$(find . -name .DS_Store -print | sort)"
fi
if [[ -n "$ds_store_files" ]]; then
  printf 'repo hygiene failed: remove Finder metadata files:\n' >&2
  printf '%s\n' "$ds_store_files" | sed 's/^/  /' >&2
  exit 1
fi

if [[ "$scope" == --git-visible ]]; then
  if git ls-files --cached --others --exclude-standard | grep -E '^tmp/' >/dev/null; then
    fail "tmp/ contains files visible to Git"
  fi
elif [[ -d tmp ]]; then
  if find tmp -mindepth 1 -print -quit | grep -q .; then
    fail "tmp/ contains generated artifacts; remove it or keep transient outputs outside the repo"
  fi
fi

copied_skill_dirs="$(
  find . \
    -path './.build' -prune -o \
    -path './dist' -prune -o \
    -path './skills' -prune -o \
    -type d \( \
      -name scientific-data-analysis -o \
      -name scientific-data-astro -o \
      -name scientific-data-documents -o \
      -name scientific-data-notebooks -o \
      -name scientific-data-maintainer \
    \) -print | sort
)"
if [[ -n "$copied_skill_dirs" ]]; then
  printf 'repo hygiene failed: installed skill directories must stay external, not copied into the app repo:\n' >&2
  printf '%s\n' "$copied_skill_dirs" | sed 's/^/  /' >&2
  exit 1
fi

if [[ -e distribution/skill-manifest.json || -e skills || -L skills ]]; then
  python3 "$ROOT_DIR/script/check_distribution_snapshot.py" || fail "distribution skill snapshot failed verification"
fi

echo "Scientific Workbench repo hygiene checks passed."
