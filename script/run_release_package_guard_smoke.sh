#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientificworkbench-package-guard.XXXXXX")"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "release package guard smoke failed: $*" >&2
  exit 1
}

make_repo() {
  local name="$1"
  local repo="$TMP_ROOT/$name"
  mkdir -p "$repo/script"
  cp "$ROOT_DIR/script/package_release.sh" "$repo/script/package_release.sh"
  cp "$ROOT_DIR/script/resolve_skill_registry_evidence.py" \
    "$repo/script/resolve_skill_registry_evidence.py"
  chmod +x \
    "$repo/script/package_release.sh" \
    "$repo/script/resolve_skill_registry_evidence.py"
  printf '%s\n' 'dist/' >"$repo/.gitignore"
  printf '%s\n' 'original' >"$repo/tracked.txt"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'set -euo pipefail' \
    'touch "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/build-invoked"' \
    'exit 99' \
    >"$repo/script/build_and_run.sh"
  chmod +x "$repo/script/build_and_run.sh"
  git -C "$repo" init -q
  git -C "$repo" config user.name "Scientific Workbench Smoke"
  git -C "$repo" config user.email "smoke@example.invalid"
  git -C "$repo" add .
  git -C "$repo" commit -q -m "fixture"
  printf '%s\n' "$repo"
}

expect_rejected() {
  local name="$1"
  local repo="$2"
  local expected="$3"
  local log="$TMP_ROOT/${name}.log"
  if "$repo/script/package_release.sh" \
    --local \
    --version 9.9.9 \
    --build "$name" \
    --run-quality \
    >"$log" 2>&1; then
    fail "$name was accepted"
  fi
  if ! grep -Fq "$expected" "$log"; then
    cat "$log" >&2
    fail "$name failed for an unexpected reason; expected: $expected"
  fi
  [[ ! -e "$repo/build-invoked" ]] || fail "$name reached the app build"
}

REPO="$(make_repo dirty-after-quality)"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'printf "%s\n" changed >>tracked.txt' \
  >"$REPO/script/run_quality_gate.sh"
chmod +x "$REPO/script/run_quality_gate.sh"
git -C "$REPO" add script/run_quality_gate.sh
git -C "$REPO" commit -q -m "quality fixture"
expect_rejected \
  "dirty-after-quality" \
  "$REPO" \
  "release packaging requires a clean worktree"

REPO="$(make_repo revision-after-quality)"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  'printf "%s\n" committed-by-gate >>tracked.txt' \
  'git add tracked.txt' \
  'git commit -q -m "unexpected gate commit"' \
  >"$REPO/script/run_quality_gate.sh"
chmod +x "$REPO/script/run_quality_gate.sh"
git -C "$REPO" add script/run_quality_gate.sh
git -C "$REPO" commit -q -m "quality fixture"
expect_rejected \
  "revision-after-quality" \
  "$REPO" \
  "source revision changed during release validation"

echo "Scientific Workbench release package guard smoke passed."
