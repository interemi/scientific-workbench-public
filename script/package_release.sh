#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DISPLAY_NAME="Scientific Workbench"
APP_BUNDLE="$ROOT_DIR/dist/$APP_DISPLAY_NAME.app"
RELEASE_ROOT="$ROOT_DIR/dist/release"
BUNDLE_ID="com.emilio.scientific-workbench"
MINIMUM_MACOS="14.0"
MANIFEST_SCHEMA_VERSION=2
REGISTRY_EVIDENCE_RESOLVER="$ROOT_DIR/script/resolve_skill_registry_evidence.py"

VERSION="${VERSION:-1.0.0}"
BUILD_NUMBER="${BUILD_NUMBER:-$(date +%Y%m%d%H%M)}"
INTEGRATED_RELEASE="${INTEGRATED_RELEASE:-2.0}"
SKILL_RELEASE="${SKILL_RELEASE:-2.8}"
SIGN=0
NOTARIZE=0
CODESIGN_IDENTITY="${CODESIGN_IDENTITY:-}"
NOTARYTOOL_PROFILE="${NOTARYTOOL_PROFILE:-}"
RUN_QUALITY=0

usage() {
  cat >&2 <<'USAGE'
usage: script/package_release.sh [--local] [--sign] [--notarize]
                                 [--identity "Developer ID Application: ..."]
                                 [--notary-profile profile-name]
                                 [--version 1.0.0] [--build 123]
                                 [--integrated-release 2.0]
                                 [--skill-release 2.8]
                                 [--run-quality]

Modes:
  --local       Build and zip an unsigned local release artifact. This is the default.
  --sign        Sign the app with a Developer ID Application identity.
  --notarize    Sign, submit with notarytool, staple, validate, and zip.

Notarization expects a stored notarytool keychain profile:
  xcrun notarytool store-credentials "profile-name" --apple-id ... --team-id ... --password ...
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --local)
      SIGN=0
      NOTARIZE=0
      shift
      ;;
    --sign)
      SIGN=1
      shift
      ;;
    --notarize)
      SIGN=1
      NOTARIZE=1
      shift
      ;;
    --identity)
      CODESIGN_IDENTITY="${2:-}"
      shift 2
      ;;
    --notary-profile)
      NOTARYTOOL_PROFILE="${2:-}"
      shift 2
      ;;
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --build)
      BUILD_NUMBER="${2:-}"
      shift 2
      ;;
    --integrated-release)
      INTEGRATED_RELEASE="${2:-}"
      shift 2
      ;;
    --skill-release)
      SKILL_RELEASE="${2:-}"
      shift 2
      ;;
    --run-quality)
      RUN_QUALITY=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ "$SIGN" == "1" && -z "$CODESIGN_IDENTITY" ]]; then
  echo "package_release: --sign/--notarize requires --identity or CODESIGN_IDENTITY." >&2
  exit 2
fi

if [[ "$NOTARIZE" == "1" && -z "$NOTARYTOOL_PROFILE" ]]; then
  echo "package_release: --notarize requires --notary-profile or NOTARYTOOL_PROFILE." >&2
  exit 2
fi

if [[ ! "$VERSION" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]]; then
  echo "package_release: --version must be numeric, for example 1, 1.0, or 1.0.0." >&2
  exit 2
fi

if [[ ! "$BUILD_NUMBER" =~ ^[0-9A-Za-z.-]+$ ]]; then
  echo "package_release: --build may contain only letters, numbers, dots, and hyphens." >&2
  exit 2
fi

if [[ ! "$INTEGRATED_RELEASE" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]]; then
  echo "package_release: --integrated-release must be numeric, for example 2.0." >&2
  exit 2
fi

if [[ ! "$SKILL_RELEASE" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]]; then
  echo "package_release: --skill-release must be numeric, for example 2.8." >&2
  exit 2
fi

command -v swift >/dev/null || { echo "package_release: swift is required." >&2; exit 2; }
command -v ditto >/dev/null || { echo "package_release: ditto is required." >&2; exit 2; }
[[ -x "$REGISTRY_EVIDENCE_RESOLVER" ]] || {
  echo "package_release: missing executable registry evidence resolver." >&2
  exit 2
}

cd "$ROOT_DIR"

git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  echo "package_release: a Git worktree is required for traceable release packaging." >&2
  exit 2
}

assert_clean_worktree() {
  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain --untracked-files=normal)" ]]; then
    echo "package_release: release packaging requires a clean worktree so the archive maps to one commit." >&2
    return 1
  fi
}

assert_source_unchanged() {
  assert_clean_worktree || return 1
  local current_revision
  current_revision="$(git -C "$ROOT_DIR" rev-parse HEAD)"
  if [[ "$current_revision" != "$INITIAL_SOURCE_REVISION" ]]; then
    echo "package_release: source revision changed during release validation." >&2
    return 1
  fi
}

assert_clean_worktree
INITIAL_SOURCE_REVISION="$(git -C "$ROOT_DIR" rev-parse HEAD)"

RELEASE_DIR="$RELEASE_ROOT/$VERSION"
mkdir -p "$RELEASE_DIR"
UPLOAD_ARCHIVE="$RELEASE_DIR/Scientific_Workbench_${VERSION}_${BUILD_NUMBER}_notary_upload.zip"
FINAL_ARCHIVE="$RELEASE_DIR/Scientific_Workbench_${VERSION}_${BUILD_NUMBER}_macOS.zip"
MANIFEST_PATH="$RELEASE_DIR/Scientific_Workbench_${VERSION}_${BUILD_NUMBER}_manifest.json"

for candidate in "$FINAL_ARCHIVE" "$MANIFEST_PATH"; do
  if [[ -e "$candidate" ]]; then
    echo "package_release: refusing to overwrite existing release evidence: $candidate" >&2
    echo "package_release: choose a new --build identifier." >&2
    exit 2
  fi
done

if [[ "$NOTARIZE" == "1" && -e "$UPLOAD_ARCHIVE" ]]; then
  echo "package_release: refusing to overwrite existing notarization upload: $UPLOAD_ARCHIVE" >&2
  exit 2
fi

if [[ "$RUN_QUALITY" == "1" ]]; then
  "$ROOT_DIR/script/run_quality_gate.sh"
fi

assert_source_unchanged
SOURCE_REVISION="$(git -C "$ROOT_DIR" rev-parse HEAD)"
SOURCE_REVISION_SHORT="$(git -C "$ROOT_DIR" rev-parse --short=12 HEAD)"
GIT_BRANCH="$(git -C "$ROOT_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || echo detached)"
REGISTRY_EVIDENCE_BEFORE="$("$REGISTRY_EVIDENCE_RESOLVER")"

APP_VERSION="$VERSION" APP_BUILD="$BUILD_NUMBER" SWIFT_CONFIGURATION=release \
  "$ROOT_DIR/script/build_and_run.sh" --build

if [[ "$SIGN" == "1" ]]; then
  /usr/bin/codesign \
    --force \
    --timestamp \
    --options runtime \
    --sign "$CODESIGN_IDENTITY" \
    "$APP_BUNDLE"
  /usr/bin/codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"
fi

"$ROOT_DIR/script/verify_app_bundle.sh" "$APP_BUNDLE"

if [[ "$NOTARIZE" == "1" ]]; then
  /usr/bin/ditto -c -k --keepParent "$APP_BUNDLE" "$UPLOAD_ARCHIVE"
  /usr/bin/xcrun notarytool submit "$UPLOAD_ARCHIVE" \
    --keychain-profile "$NOTARYTOOL_PROFILE" \
    --wait
  /usr/bin/xcrun stapler staple "$APP_BUNDLE"
  /usr/bin/xcrun stapler validate "$APP_BUNDLE"
  /usr/sbin/spctl --assess --type execute --verbose "$APP_BUNDLE"
fi

GENERATED_RELEASE_EVIDENCE=("$FINAL_ARCHIVE" "$MANIFEST_PATH")
cleanup_failed_release() {
  local status=$?
  trap - EXIT
  if [[ "$status" != "0" ]]; then
    for generated_path in "${GENERATED_RELEASE_EVIDENCE[@]}"; do
      [[ -e "$generated_path" ]] && rm -f -- "$generated_path"
    done
  fi
  exit "$status"
}
trap cleanup_failed_release EXIT
/usr/bin/ditto -c -k --keepParent "$APP_BUNDLE" "$FINAL_ARCHIVE"

assert_source_unchanged
REGISTRY_EVIDENCE_AFTER="$("$REGISTRY_EVIDENCE_RESOLVER")"
if [[ "$REGISTRY_EVIDENCE_AFTER" != "$REGISTRY_EVIDENCE_BEFORE" ]]; then
  echo "package_release: installed skill registry changed during packaging." >&2
  exit 2
fi

SHA256="$(/usr/bin/shasum -a 256 "$FINAL_ARCHIVE" | awk '{print $1}')"
ARCHIVE_FILE="$(basename "$FINAL_ARCHIVE")"
ARCHIVE_SIZE_BYTES="$(/usr/bin/stat -f "%z" "$FINAL_ARCHIVE")"
SWIFT_VERSION="$(swift --version | head -n 1)"
HOST_MACOS="$(/usr/bin/sw_vers -productVersion)"
HOST_ARCH="$(/usr/bin/uname -m)"
CREATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
DOCUS_BENCHMARK_RAN=false
if [[ "$RUN_QUALITY" == "1" && "${RUN_DOCUS_BENCHMARK:-0}" == "1" ]]; then
  DOCUS_BENCHMARK_RAN=true
fi
/usr/bin/python3 - \
  "$MANIFEST_PATH" "$MANIFEST_SCHEMA_VERSION" "$BUNDLE_ID" "$VERSION" "$BUILD_NUMBER" "$MINIMUM_MACOS" \
  "$ARCHIVE_FILE" "$ARCHIVE_SIZE_BYTES" "$SHA256" "$SIGN" "$NOTARIZE" \
  "$RUN_QUALITY" "$SOURCE_REVISION" "$SOURCE_REVISION_SHORT" "$GIT_BRANCH" \
  "$CREATED_AT" "$INTEGRATED_RELEASE" "$SKILL_RELEASE" "$SWIFT_VERSION" \
  "$HOST_MACOS" "$HOST_ARCH" "$DOCUS_BENCHMARK_RAN" \
  "${DOCUS_BENCHMARK_MODE:-plan}" "$REGISTRY_EVIDENCE_AFTER" <<'PY'
import json
import sys
from pathlib import Path

(
    manifest_path,
    manifest_schema_version,
    bundle_id,
    version,
    build,
    minimum_macos,
    archive_file,
    archive_size_bytes,
    sha256,
    sign,
    notarize,
    run_quality,
    source_revision,
    source_revision_short,
    git_branch,
    created_at,
    integrated_release,
    skill_release,
    swift_version,
    host_macos,
    host_arch,
    docus_benchmark_ran,
    docus_benchmark_mode,
    registry_evidence_json,
) = sys.argv[1:]

registry_evidence = json.loads(registry_evidence_json)

payload = {
    "manifest_schema_version": int(manifest_schema_version),
    "app_name": "Scientific Workbench",
    "bundle_identifier": bundle_id,
    "version": version,
    "build": build,
    "integrated_release": integrated_release,
    "skill_release": skill_release,
    "minimum_macos": minimum_macos,
    "archive_file": archive_file,
    "archive_relative_path": f"{version}/{archive_file}",
    "archive_size_bytes": int(archive_size_bytes),
    "sha256": sha256,
    "signed": sign == "1",
    "notarized": notarize == "1",
    "quality_gate_ran": run_quality == "1",
    "source_revision": source_revision,
    "source_revision_short": source_revision_short,
    "source_dirty": False,
    "git_branch": git_branch,
    "created_at": created_at,
    "environment": {
        "swift_version": swift_version,
        "macos_version": host_macos,
        "architecture": host_arch,
    },
    "validation": {
        "quality_gate_ran": run_quality == "1",
        "docus_benchmark_ran": docus_benchmark_ran == "true",
        "docus_benchmark_mode": docus_benchmark_mode if docus_benchmark_ran == "true" else None,
    },
    "skill_registry_sha256": registry_evidence["skill_registry_sha256"],
    "skill_registry_stub_sha256": registry_evidence[
        "skill_registry_stub_sha256"
    ],
    "skill_registry_relative_path": registry_evidence[
        "skill_registry_relative_path"
    ],
    "skill_registry_chain": registry_evidence["skill_registry_chain"],
}

Path(manifest_path).write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

"$ROOT_DIR/script/verify_release_manifest.sh" "$MANIFEST_PATH"
"$ROOT_DIR/script/verify_release_archive.sh" "$MANIFEST_PATH"
trap - EXIT

echo "Scientific Workbench release package ready:"
echo "  $FINAL_ARCHIVE"
echo "  manifest: $MANIFEST_PATH"
echo "  sha256: $SHA256"
