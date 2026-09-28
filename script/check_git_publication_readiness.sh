#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

fail() {
  echo "git publication readiness failed: $*" >&2
  exit 1
}

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "not inside a Git repository"

"$ROOT_DIR/script/check_repo_hygiene.sh" --git-visible >/dev/null || fail "repository hygiene check failed"

candidate_list="$(mktemp "${TMPDIR:-/tmp}/scientific-workbench-git-candidates.XXXXXX")"
trap 'rm -f "$candidate_list"' EXIT
git ls-files --cached --others --exclude-standard >"$candidate_list"

if [[ ! -s "$candidate_list" ]]; then
  fail "no publishable files are visible to Git"
fi

blocked_paths="$(
  grep -E '(^|/)(\.codex|\.build|dist|tmp)(/|$)' "$candidate_list" || true
)"
if [[ -n "$blocked_paths" ]]; then
  printf 'git publication readiness failed: local/generated paths are visible to Git:\n' >&2
  printf '%s\n' "$blocked_paths" | sed 's/^/  /' >&2
  exit 1
fi

credential_paths="$(grep -iE '(^|/)\.env($|\.)|\.(pem|key|p12|pfx)$' "$candidate_list" | grep -ivE '(^|/)\.env\.example$' || true)"
if [[ -n "$credential_paths" ]]; then
  printf 'git publication readiness failed: credential/signing files are visible to Git:\n' >&2
  printf '%s\n' "$credential_paths" | sed 's/^/  /' >&2
  exit 1
fi

dependency_payloads="$(
  grep -iE '(^|/)(DOCUS|\.venv|venv)(/|$)|\.(whl|onnx|gguf|safetensors|dmg|pkg)$|\.app/|\.xcarchive/' "$candidate_list" || true
)"
if [[ -n "$dependency_payloads" ]]; then
  printf 'git publication readiness failed: bundled dependency, model, environment, or app payloads are visible to Git:\n' >&2
  printf '%s\n' "$dependency_payloads" | sed 's/^/  /' >&2
  exit 1
fi

copied_skill_paths="$(
  grep -E '(^|/)(scientific-data-analysis|scientific-data-astro|scientific-data-documents|scientific-data-notebooks|scientific-data-maintainer)(/|$)' "$candidate_list" \
    | grep -v -E '^skills/(scientific-data-analysis|scientific-data-astro|scientific-data-documents|scientific-data-notebooks|scientific-data-maintainer)/' || true
)"
if [[ -n "$copied_skill_paths" ]]; then
  printf 'git publication readiness failed: installed skill folders must not be published from the app repo:\n' >&2
  printf '%s\n' "$copied_skill_paths" | sed 's/^/  /' >&2
  exit 1
fi

large_files="$(
  while IFS= read -r file; do
    [[ -f "$file" ]] || continue
    size="$(stat -f%z "$file")"
    if [[ "$size" -gt 5242880 ]]; then
      printf '%s (%s bytes)\n' "$file" "$size"
    fi
  done <"$candidate_list"
)"
if [[ -n "$large_files" ]]; then
  printf 'git publication readiness failed: large files need explicit review before publishing:\n' >&2
  printf '%s\n' "$large_files" | sed 's/^/  /' >&2
  exit 1
fi

python3 "$ROOT_DIR/script/audit_publication_history.py" --check-secrets || fail "unreviewed possible secrets; run the audit with --output to inspect redacted locations"

if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "Scientific Workbench Git publication readiness passed; no baseline commit exists yet."
else
  echo "Scientific Workbench Git publication readiness passed."
fi
