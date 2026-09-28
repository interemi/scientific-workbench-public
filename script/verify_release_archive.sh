#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DISPLAY_NAME="Scientific Workbench"
MANIFEST="${1:-}"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientificworkbench-release-archive.XXXXXX")"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "release archive verify failed: $*" >&2
  exit 1
}

if [[ -z "$MANIFEST" ]]; then
  MANIFEST="$(/usr/bin/python3 - "$ROOT_DIR/dist/release" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
candidates = list(root.glob("**/manifest.json")) + list(root.glob("**/*_manifest.json"))
if candidates:
    print(max(candidates, key=lambda path: path.stat().st_mtime))
PY
)"
fi

[[ -n "$MANIFEST" ]] || fail "no manifest path supplied and no release manifest found"
[[ -f "$MANIFEST" ]] || fail "missing manifest at $MANIFEST"

"$ROOT_DIR/script/verify_release_manifest.sh" "$MANIFEST"

ARCHIVE_PATH="$(/usr/bin/python3 - "$MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1]).resolve()
with manifest_path.open("r", encoding="utf-8") as handle:
    payload = json.load(handle)
print(manifest_path.parent / payload["archive_file"])
PY
)"

[[ -f "$ARCHIVE_PATH" ]] || fail "missing archive at $ARCHIVE_PATH"

/usr/bin/ditto -x -k "$ARCHIVE_PATH" "$TMP_ROOT"

EXTRACTED_APP="$TMP_ROOT/$APP_DISPLAY_NAME.app"
[[ -d "$EXTRACTED_APP" ]] || fail "archive did not contain $APP_DISPLAY_NAME.app at top level"

TOP_LEVEL_ENTRIES="$(/usr/bin/python3 - "$TMP_ROOT" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
print("\n".join(sorted(path.name for path in root.iterdir())))
PY
)"
[[ "$TOP_LEVEL_ENTRIES" == "$APP_DISPLAY_NAME.app" ]] || {
  fail "archive must contain only $APP_DISPLAY_NAME.app at top level"
}

IFS=$'\t' read -r MANIFEST_VERSION MANIFEST_BUILD < <(
  /usr/bin/python3 - "$MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(f"{payload['version']}\t{payload['build']}")
PY
)

INFO_PLIST="$EXTRACTED_APP/Contents/Info.plist"
[[ -f "$INFO_PLIST" ]] || fail "extracted app is missing Info.plist"
BUNDLE_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$INFO_PLIST" 2>/dev/null || true)"
BUNDLE_BUILD="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$INFO_PLIST" 2>/dev/null || true)"
[[ "$BUNDLE_VERSION" == "$MANIFEST_VERSION" ]] || {
  fail "CFBundleShortVersionString does not match manifest version"
}
[[ "$BUNDLE_BUILD" == "$MANIFEST_BUILD" ]] || {
  fail "CFBundleVersion does not match manifest build"
}

"$ROOT_DIR/script/verify_app_bundle.sh" "$EXTRACTED_APP"

echo "Scientific Workbench release archive verified."
