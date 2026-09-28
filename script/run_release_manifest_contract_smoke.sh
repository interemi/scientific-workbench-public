#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERIFY_MANIFEST="$ROOT_DIR/script/verify_release_manifest.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientificworkbench-manifest-contract.XXXXXX")"
VERSION="9.9.9"
BUILD="contract-smoke"
ARCHIVE_FILE="Scientific_Workbench_${VERSION}_${BUILD}_macOS.zip"
MANIFEST_FILE="Scientific_Workbench_${VERSION}_${BUILD}_manifest.json"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "release manifest contract smoke failed: $*" >&2
  exit 1
}

[[ -x "$VERIFY_MANIFEST" ]] || fail "verify_release_manifest.sh is not executable"

VALID_DIR="$TMP_ROOT/valid"
mkdir -p "$VALID_DIR"

/usr/bin/python3 - "$VALID_DIR" "$VERSION" "$BUILD" "$ARCHIVE_FILE" "$MANIFEST_FILE" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
version, build, archive_file, manifest_file = sys.argv[2:]
archive = root / archive_file
archive.write_bytes(b"Scientific Workbench schema-2 manifest contract fixture\n")
payload = {
    "manifest_schema_version": 2,
    "app_name": "Scientific Workbench",
    "bundle_identifier": "com.emilio.scientific-workbench",
    "version": version,
    "build": build,
    "integrated_release": "2.0",
    "skill_release": "2.8",
    "minimum_macos": "14.0",
    "archive_file": archive_file,
    "archive_relative_path": f"{version}/{archive_file}",
    "archive_size_bytes": archive.stat().st_size,
    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "signed": False,
    "notarized": False,
    "quality_gate_ran": False,
    "source_revision": "0123456789abcdef0123456789abcdef01234567",
    "source_revision_short": "0123456789ab",
    "source_dirty": False,
    "git_branch": "contract-smoke",
    "created_at": "2026-07-15T00:00:00Z",
    "environment": {
        "swift_version": "Swift contract fixture",
        "macos_version": "14.0",
        "architecture": "arm64",
    },
    "validation": {
        "quality_gate_ran": False,
        "docus_benchmark_ran": False,
        "docus_benchmark_mode": None,
    },
    "skill_registry_sha256": hashlib.sha256(b"canonical registry fixture").hexdigest(),
    "skill_registry_stub_sha256": hashlib.sha256(b"mother registry fixture").hexdigest(),
    "skill_registry_relative_path": "scientific-data-maintainer/canonical.yaml",
    "skill_registry_chain": [
        {
            "relative_path": "scientific-data-analysis/public_surface_registry.yaml",
            "sha256": hashlib.sha256(b"mother registry fixture").hexdigest(),
        },
        {
            "relative_path": "scientific-data-maintainer/canonical.yaml",
            "sha256": hashlib.sha256(b"canonical registry fixture").hexdigest(),
        },
    ],
}
(root / manifest_file).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

VALID_MANIFEST="$VALID_DIR/$MANIFEST_FILE"
"$VERIFY_MANIFEST" "$VALID_MANIFEST" >/dev/null

clone_valid_case() {
  local name="$1"
  local case_dir="$TMP_ROOT/$name"
  mkdir -p "$case_dir"
  cp "$VALID_DIR/$ARCHIVE_FILE" "$case_dir/$ARCHIVE_FILE"
  cp "$VALID_MANIFEST" "$case_dir/$MANIFEST_FILE"
  printf '%s\n' "$case_dir"
}

mutate_manifest() {
  local manifest="$1"
  local mutation="$2"
  /usr/bin/python3 - "$manifest" "$mutation" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
mutation = sys.argv[2]
payload = json.loads(path.read_text(encoding="utf-8"))

if mutation == "remove_schema":
    payload.pop("manifest_schema_version", None)
elif mutation == "schema_one":
    payload["manifest_schema_version"] = 1
elif mutation == "source_dirty":
    payload["source_dirty"] = True
elif mutation == "missing_environment":
    payload.pop("environment", None)
elif mutation == "validation_conflict":
    payload["validation"]["quality_gate_ran"] = True
elif mutation == "registry_null":
    payload["skill_registry_sha256"] = None
elif mutation == "registry_escape":
    payload["skill_registry_relative_path"] = "../outside.yaml"
else:
    raise SystemExit(f"unknown manifest mutation: {mutation}")

path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

expect_rejected() {
  local name="$1"
  local manifest="$2"
  local expected="$3"
  local output="$TMP_ROOT/${name}.log"
  if "$VERIFY_MANIFEST" "$manifest" >"$output" 2>&1; then
    fail "$name was accepted"
  fi
  if ! grep -Fq "$expected" "$output"; then
    cat "$output" >&2
    fail "$name failed for an unexpected reason; expected: $expected"
  fi
}

CASE_DIR="$(clone_valid_case missing-schema)"
mutate_manifest "$CASE_DIR/$MANIFEST_FILE" remove_schema
expect_rejected \
  "missing schema declaration" \
  "$CASE_DIR/$MANIFEST_FILE" \
  "non-legacy release manifests must declare manifest_schema_version"

CASE_DIR="$(clone_valid_case explicit-schema-downgrade)"
mutate_manifest "$CASE_DIR/$MANIFEST_FILE" schema_one
expect_rejected \
  "explicit schema downgrade" \
  "$CASE_DIR/$MANIFEST_FILE" \
  "schema v1 is reserved for recognized immutable historical evidence"

RENAMED_DIR="$TMP_ROOT/renamed-downgrade/$VERSION"
mkdir -p "$RENAMED_DIR"
cp "$VALID_DIR/$ARCHIVE_FILE" "$RENAMED_DIR/$ARCHIVE_FILE"
cp "$VALID_MANIFEST" "$RENAMED_DIR/manifest.json"
mutate_manifest "$RENAMED_DIR/manifest.json" schema_one
expect_rejected \
  "renamed schema downgrade" \
  "$RENAMED_DIR/manifest.json" \
  "schema v1 is reserved for recognized immutable historical evidence"

CASE_DIR="$(clone_valid_case archive-tamper)"
/usr/bin/python3 - "$CASE_DIR/$ARCHIVE_FILE" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = bytearray(path.read_bytes())
data[len(data) // 2] ^= 1
path.write_bytes(data)
PY
expect_rejected \
  "same-size archive tamper" \
  "$CASE_DIR/$MANIFEST_FILE" \
  "sha256 mismatch"

CASE_DIR="$(clone_valid_case dirty-source)"
mutate_manifest "$CASE_DIR/$MANIFEST_FILE" source_dirty
expect_rejected \
  "dirty source evidence" \
  "$CASE_DIR/$MANIFEST_FILE" \
  "schema v2 release manifests must record source_dirty as false"

CASE_DIR="$(clone_valid_case missing-v2-key)"
mutate_manifest "$CASE_DIR/$MANIFEST_FILE" missing_environment
expect_rejected \
  "missing schema v2 key" \
  "$CASE_DIR/$MANIFEST_FILE" \
  "missing schema v2 keys: environment"

CASE_DIR="$(clone_valid_case validation-conflict)"
mutate_manifest "$CASE_DIR/$MANIFEST_FILE" validation_conflict
expect_rejected \
  "validation evidence conflict" \
  "$CASE_DIR/$MANIFEST_FILE" \
  "validation.quality_gate_ran conflicts with quality_gate_ran"

CASE_DIR="$(clone_valid_case missing-registry-digest)"
mutate_manifest "$CASE_DIR/$MANIFEST_FILE" registry_null
expect_rejected \
  "missing canonical registry digest" \
  "$CASE_DIR/$MANIFEST_FILE" \
  "skill_registry_sha256 must be a lowercase SHA-256"

CASE_DIR="$(clone_valid_case registry-path-escape)"
mutate_manifest "$CASE_DIR/$MANIFEST_FILE" registry_escape
expect_rejected \
  "registry path escape" \
  "$CASE_DIR/$MANIFEST_FILE" \
  "skill_registry_relative_path must stay within the installed skills root"

LEGACY_DIR="$TMP_ROOT/legacy/$VERSION"
mkdir -p "$LEGACY_DIR"
cp "$VALID_DIR/$ARCHIVE_FILE" "$LEGACY_DIR/$ARCHIVE_FILE"
/usr/bin/python3 - "$VALID_MANIFEST" "$LEGACY_DIR/manifest.json" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
payload = json.loads(source.read_text(encoding="utf-8"))
for key in [
    "manifest_schema_version",
    "integrated_release",
    "skill_release",
    "source_revision_short",
    "source_dirty",
    "git_branch",
    "environment",
    "validation",
    "skill_registry_sha256",
    "skill_registry_stub_sha256",
    "skill_registry_relative_path",
    "skill_registry_chain",
]:
    payload.pop(key, None)
target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
expect_rejected \
  "fabricated legacy manifest" \
  "$LEGACY_DIR/manifest.json" \
  "unrecognized legacy schema-1 evidence; new manifests require schema 2"

HISTORICAL_MANIFEST="$ROOT_DIR/dist/release/1.0.0/manifest.json"
if [[ -f "$HISTORICAL_MANIFEST" ]]; then
  "$VERIFY_MANIFEST" "$HISTORICAL_MANIFEST" >/dev/null
fi

echo "Scientific Workbench release manifest contract smoke passed."
