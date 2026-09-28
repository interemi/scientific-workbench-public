#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DISPLAY_NAME="Scientific Workbench"
APP_EXECUTABLE_NAME="Scientific Workbench"
EXPECTED_BUNDLE_ID="com.emilio.scientific-workbench"
APP_BUNDLE="${1:-$ROOT_DIR/dist/$APP_DISPLAY_NAME.app}"
INFO_PLIST="$APP_BUNDLE/Contents/Info.plist"
APP_BINARY="$APP_BUNDLE/Contents/MacOS/$APP_EXECUTABLE_NAME"
APP_ICON="$APP_BUNDLE/Contents/Resources/AppIcon.icns"
USER_GUIDE="$APP_BUNDLE/Contents/Resources/Guides/Scientific_Workbench_User_Guide.md"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientificworkbench-bundle-verify.XXXXXX")"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

fail() {
  echo "bundle verify failed: $*" >&2
  exit 1
}

plist_value() {
  /usr/libexec/PlistBuddy -c "Print :$1" "$INFO_PLIST" 2>/dev/null || true
}

verify_clean_codesign() {
  local bundle="$1"
  local verify_log
  verify_log="$(mktemp "${TMPDIR:-/tmp}/scientific-workbench-codesign.XXXXXX")"
  for _ in {1..10}; do
    /usr/bin/xattr -cr "$bundle" 2>/dev/null || true
    if /usr/bin/codesign --verify --deep --strict "$bundle" >/dev/null 2>"$verify_log"; then
      rm -f "$verify_log"
      return 0
    fi
    if ! grep -q "resource fork, Finder information, or similar detritus not allowed" "$verify_log"; then
      cat "$verify_log" >&2
      rm -f "$verify_log"
      return 1
    fi
    sleep 0.25
  done
  rm -f "$verify_log"
  /usr/bin/xattr -cr "$bundle" 2>/dev/null || true
  /usr/bin/codesign --verify --deep --strict "$bundle" >/dev/null
}

[[ -d "$APP_BUNDLE" ]] || fail "missing app bundle at $APP_BUNDLE"
[[ -f "$INFO_PLIST" ]] || fail "missing Info.plist"
[[ -x "$APP_BINARY" ]] || fail "missing executable at $APP_BINARY"
[[ -f "$APP_ICON" ]] || fail "missing AppIcon.icns"
[[ -f "$USER_GUIDE" ]] || fail "missing bundled user guide"

[[ "$(plist_value CFBundleExecutable)" == "$APP_EXECUTABLE_NAME" ]] || fail "unexpected CFBundleExecutable"
[[ "$(plist_value CFBundleIdentifier)" == "$EXPECTED_BUNDLE_ID" ]] || fail "unexpected CFBundleIdentifier"
[[ "$(plist_value CFBundleName)" == "$APP_DISPLAY_NAME" ]] || fail "unexpected CFBundleName"
[[ "$(plist_value CFBundleDisplayName)" == "$APP_DISPLAY_NAME" ]] || fail "unexpected CFBundleDisplayName"
[[ "$(plist_value CFBundlePackageType)" == "APPL" ]] || fail "unexpected CFBundlePackageType"
[[ "$(plist_value CFBundleIconFile)" == "AppIcon" ]] || fail "unexpected CFBundleIconFile"
[[ -n "$(plist_value CFBundleVersion)" ]] || fail "missing CFBundleVersion"
SHORT_VERSION="$(plist_value CFBundleShortVersionString)"
[[ -n "$SHORT_VERSION" ]] || fail "missing CFBundleShortVersionString"
[[ "$SHORT_VERSION" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]] || fail "CFBundleShortVersionString must be numeric"
[[ "$(plist_value LSMinimumSystemVersion)" == "14.0" ]] || fail "unexpected LSMinimumSystemVersion"
[[ -s "$APP_ICON" ]] || fail "AppIcon.icns is empty"
[[ -s "$USER_GUIDE" ]] || fail "bundled user guide is empty"

if ! grep -q "Scientific Workbench User Guide" "$USER_GUIDE"; then
  fail "bundled user guide has unexpected contents"
fi

if ! file "$APP_ICON" | grep -q "Mac OS X icon"; then
  fail "AppIcon.icns is not recognized as a macOS icon"
fi

if ! verify_clean_codesign "$APP_BUNDLE"; then
  fail "app bundle code signature is invalid"
fi

FIXTURE_ROOT="$TMP_ROOT/fixture"
OUTPUT_ROOT="$TMP_ROOT/output"
TRANSCRIPT="$OUTPUT_ROOT/transcript.json"
mkdir -p "$FIXTURE_ROOT" "$OUTPUT_ROOT"
printf "x,y\n1,2\n" >"$FIXTURE_ROOT/table.csv"

/usr/bin/open -n "$APP_BUNDLE" --args \
  --agent-input "$FIXTURE_ROOT" \
  --agent-mode workflow \
  --agent-local-planner \
  --agent-output-root "$OUTPUT_ROOT" \
  --agent-prompt "Verify packaged app planning without touching originals." \
  --agent-transcript-json "$TRANSCRIPT" \
  --agent-isolated-session \
  --agent-exit-after-run

for _ in {1..80}; do
  [[ -f "$TRANSCRIPT" ]] && break
  sleep 0.25
done
[[ -f "$TRANSCRIPT" ]] || fail "headless bundle launch did not write transcript"

/usr/bin/python3 - "$TRANSCRIPT" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as handle:
    payload = json.load(handle)

plan = payload.get("agent_plan")
if not isinstance(plan, dict):
    raise SystemExit("missing structured agent_plan")
if plan.get("source") not in {"local", "skillRouter"}:
    raise SystemExit(f"unexpected plan source: {plan.get('source')!r}")

steps = plan.get("steps")
if not isinstance(steps, list) or not steps:
    raise SystemExit("missing plan steps")
ids = [step.get("capability_id") for step in steps]
if "profile_table" not in ids:
    raise SystemExit(f"expected profile_table in packaged smoke plan, got {ids}")
maintainer_ids = {
    "external_astro_tools_local_validation",
    "capability_probe_matrix",
    "portable_smoke_test",
    "validate_skill_samples",
    "sync_public_surface_docs",
    "skill_surface_audit",
}
if set(ids) & maintainer_ids:
    raise SystemExit(f"packaged user plan exposed maintainer capabilities: {ids}")

estimate = plan.get("estimate", {})
if estimate.get("enabled_step_count") != len([step for step in steps if step.get("is_enabled", True)]):
    raise SystemExit("estimate enabled_step_count mismatch")
PY

echo "Scientific Workbench app bundle verified."
