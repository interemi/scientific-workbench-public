#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESOLVER="$ROOT_DIR/script/resolve_skill_registry_evidence.py"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientificworkbench-registry-evidence.XXXXXX")"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "skill registry evidence smoke failed: $*" >&2
  exit 1
}

[[ -x "$RESOLVER" ]] || fail "registry evidence resolver is not executable"

write_case() {
  local case_root="$1"
  mkdir -p \
    "$case_root/scientific-data-analysis" \
    "$case_root/scientific-data-maintainer/.cache"
  printf '%s\n' \
    'canonical_registry: ../scientific-data-maintainer/public_surface_registry.yaml' \
    >"$case_root/scientific-data-analysis/public_surface_registry.yaml"
  printf '%s\n' \
    'canonical_registry: .cache/canonical.yaml' \
    >"$case_root/scientific-data-maintainer/public_surface_registry.yaml"
  printf '%s\n' \
    'entries:' \
    '  - id: fixture' \
    >"$case_root/scientific-data-maintainer/.cache/canonical.yaml"
}

VALID_ROOT="$TMP_ROOT/valid"
write_case "$VALID_ROOT"
VALID_JSON="$TMP_ROOT/valid.json"
"$RESOLVER" \
  --skills-root "$VALID_ROOT" \
  --mother-registry "$VALID_ROOT/scientific-data-analysis/public_surface_registry.yaml" \
  >"$VALID_JSON"

/usr/bin/python3 - "$VALID_JSON" <<'PY'
import json
import re
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
chain = payload.get("skill_registry_chain")
if not isinstance(chain, list) or len(chain) != 3:
    raise SystemExit(f"unexpected registry chain: {chain!r}")
if chain[0]["relative_path"] != "scientific-data-analysis/public_surface_registry.yaml":
    raise SystemExit("mother registry is not the first evidence item")
if chain[-1]["relative_path"] != "scientific-data-maintainer/.cache/canonical.yaml":
    raise SystemExit("canonical registry path was not resolved")
for item in chain:
    if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
        raise SystemExit(f"invalid digest: {item!r}")
if payload["skill_registry_stub_sha256"] != chain[0]["sha256"]:
    raise SystemExit("stub digest does not match the registry chain")
if payload["skill_registry_sha256"] != chain[-1]["sha256"]:
    raise SystemExit("canonical digest does not match the registry chain")
PY

expect_rejected() {
  local name="$1"
  local skills_root="$2"
  local mother_registry="$3"
  local expected="$4"
  local log="$TMP_ROOT/${name}.log"
  if "$RESOLVER" \
    --skills-root "$skills_root" \
    --mother-registry "$mother_registry" \
    >"$log" 2>&1; then
    fail "$name was accepted"
  fi
  if ! grep -Fq "$expected" "$log"; then
    cat "$log" >&2
    fail "$name failed for an unexpected reason; expected: $expected"
  fi
}

ESCAPE_ROOT="$TMP_ROOT/escape"
mkdir -p "$ESCAPE_ROOT/scientific-data-analysis"
printf '%s\n' 'entries: []' >"$TMP_ROOT/outside.yaml"
printf '%s\n' 'canonical_registry: ../../outside.yaml' \
  >"$ESCAPE_ROOT/scientific-data-analysis/public_surface_registry.yaml"
expect_rejected \
  "escape" \
  "$ESCAPE_ROOT" \
  "$ESCAPE_ROOT/scientific-data-analysis/public_surface_registry.yaml" \
  "escapes the installed skills root"

CYCLE_ROOT="$TMP_ROOT/cycle"
mkdir -p "$CYCLE_ROOT/scientific-data-analysis"
printf '%s\n' 'canonical_registry: second.yaml' \
  >"$CYCLE_ROOT/scientific-data-analysis/public_surface_registry.yaml"
printf '%s\n' 'canonical_registry: public_surface_registry.yaml' \
  >"$CYCLE_ROOT/scientific-data-analysis/second.yaml"
expect_rejected \
  "cycle" \
  "$CYCLE_ROOT" \
  "$CYCLE_ROOT/scientific-data-analysis/public_surface_registry.yaml" \
  "canonical_registry cycle detected"

DUPLICATE_ROOT="$TMP_ROOT/duplicate"
mkdir -p "$DUPLICATE_ROOT/scientific-data-analysis"
printf '%s\n' \
  'canonical_registry: first.yaml' \
  'canonical_registry: second.yaml' \
  >"$DUPLICATE_ROOT/scientific-data-analysis/public_surface_registry.yaml"
expect_rejected \
  "duplicate" \
  "$DUPLICATE_ROOT" \
  "$DUPLICATE_ROOT/scientific-data-analysis/public_surface_registry.yaml" \
  "multiple top-level canonical_registry values"

if [[ -f "$HOME/.codex/skills/scientific-data-analysis/public_surface_registry.yaml" ]]; then
  "$RESOLVER" >/dev/null
fi

echo "Scientific Workbench skill registry evidence smoke passed."
