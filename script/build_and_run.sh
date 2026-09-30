#!/usr/bin/env bash
set -euo pipefail

MODE="run"
APP_ARGS=()
if [[ $# -gt 0 ]]; then
  if [[ "$1" == "--" ]]; then
    shift
    APP_ARGS=("$@")
  else
    MODE="$1"
    shift
    if [[ "${1:-}" == "--" ]]; then
      shift
      APP_ARGS=("$@")
    fi
  fi
fi
if [[ "$MODE" == "--" ]]; then
  MODE="run"
  APP_ARGS=("$@")
fi
APP_DISPLAY_NAME="Scientific Workbench"
SWIFT_PRODUCT_NAME="ScientificWorkbench"
APP_EXECUTABLE_NAME="Scientific Workbench"
BUNDLE_ID="com.emilio.scientific-workbench"
MIN_SYSTEM_VERSION="14.0"
APP_VERSION="${APP_VERSION:-1.0}"
APP_BUILD="${APP_BUILD:-1}"
SWIFT_CONFIGURATION="${SWIFT_CONFIGURATION:-debug}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SWIFT_BUILD_OPTIONS=(--package-path "$ROOT_DIR")
if [[ -n "${SCIENTIFIC_WORKBENCH_SWIFT_BUILD_SYSTEM:-}" ]]; then
  SWIFT_BUILD_OPTIONS+=(--build-system "$SCIENTIFIC_WORKBENCH_SWIFT_BUILD_SYSTEM")
fi
if [[ -n "${SCIENTIFIC_WORKBENCH_SWIFT_SCRATCH_PATH:-}" ]]; then
  SWIFT_BUILD_OPTIONS+=(--scratch-path "$SCIENTIFIC_WORKBENCH_SWIFT_SCRATCH_PATH")
fi
DIST_DIR="$ROOT_DIR/dist"
APP_BUNDLE="$DIST_DIR/$APP_DISPLAY_NAME.app"
APP_CONTENTS="$APP_BUNDLE/Contents"
APP_MACOS="$APP_CONTENTS/MacOS"
APP_RESOURCES="$APP_CONTENTS/Resources"
APP_BINARY="$APP_MACOS/$APP_EXECUTABLE_NAME"
INFO_PLIST="$APP_CONTENTS/Info.plist"
APP_ICON_SOURCE="$ROOT_DIR/Resources/AppIcon.icns"

wait_for_process_exit() {
  local process_name="$1"
  for _ in {1..40}; do
    if ! pgrep -x "$process_name" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  return 1
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

/usr/bin/osascript -e "tell application \"$APP_DISPLAY_NAME\" to quit" >/dev/null 2>&1 || true
pkill -x "$APP_EXECUTABLE_NAME" >/dev/null 2>&1 || true
pkill -x "$SWIFT_PRODUCT_NAME" >/dev/null 2>&1 || true
wait_for_process_exit "$APP_EXECUTABLE_NAME" || pkill -9 -x "$APP_EXECUTABLE_NAME" >/dev/null 2>&1 || true
wait_for_process_exit "$SWIFT_PRODUCT_NAME" || pkill -9 -x "$SWIFT_PRODUCT_NAME" >/dev/null 2>&1 || true

cd "$ROOT_DIR"
swift build "${SWIFT_BUILD_OPTIONS[@]}" -c "$SWIFT_CONFIGURATION"
BUILD_BINARY="$(swift build "${SWIFT_BUILD_OPTIONS[@]}" -c "$SWIFT_CONFIGURATION" --show-bin-path)/$SWIFT_PRODUCT_NAME"

STAGING_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientific-workbench-app-build.XXXXXX")"
STAGING_APP_BUNDLE="$STAGING_ROOT/$APP_DISPLAY_NAME.app"
STAGING_CONTENTS="$STAGING_APP_BUNDLE/Contents"
STAGING_MACOS="$STAGING_CONTENTS/MacOS"
STAGING_RESOURCES="$STAGING_CONTENTS/Resources"
STAGING_BINARY="$STAGING_MACOS/$APP_EXECUTABLE_NAME"
STAGING_INFO_PLIST="$STAGING_CONTENTS/Info.plist"

mkdir -p "$STAGING_MACOS" "$STAGING_RESOURCES"
cp "$BUILD_BINARY" "$STAGING_BINARY"
chmod +x "$STAGING_BINARY"
if [[ -f "$APP_ICON_SOURCE" ]]; then
  cp "$APP_ICON_SOURCE" "$STAGING_RESOURCES/AppIcon.icns"
fi
if [[ -d "$ROOT_DIR/Guides" ]]; then
  mkdir -p "$STAGING_RESOURCES/Guides"
  cp "$ROOT_DIR"/Guides/*.md "$STAGING_RESOURCES/Guides/" 2>/dev/null || true
fi

cat >"$STAGING_INFO_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>$APP_EXECUTABLE_NAME</string>
  <key>CFBundleIdentifier</key>
  <string>$BUNDLE_ID</string>
  <key>CFBundleName</key>
  <string>$APP_DISPLAY_NAME</string>
  <key>CFBundleDisplayName</key>
  <string>$APP_DISPLAY_NAME</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleVersion</key>
  <string>$APP_BUILD</string>
  <key>CFBundleShortVersionString</key>
  <string>$APP_VERSION</string>
  <key>LSMinimumSystemVersion</key>
  <string>$MIN_SYSTEM_VERSION</string>
  <key>NSPrincipalClass</key>
  <string>NSApplication</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

/usr/bin/xattr -cr "$STAGING_APP_BUNDLE" 2>/dev/null || true
/usr/bin/codesign --force --deep --sign - "$STAGING_APP_BUNDLE" >/dev/null
/usr/bin/xattr -cr "$STAGING_APP_BUNDLE" 2>/dev/null || true

mkdir -p "$DIST_DIR"
rm -rf "$APP_BUNDLE"
mv "$STAGING_APP_BUNDLE" "$APP_BUNDLE"
rm -rf "$STAGING_ROOT"
/usr/bin/xattr -cr "$APP_BUNDLE" 2>/dev/null || true
verify_clean_codesign "$APP_BUNDLE"

open_app() {
  if [[ ${#APP_ARGS[@]} -gt 0 ]]; then
    /usr/bin/open -n "$APP_BUNDLE" --args "${APP_ARGS[@]}"
  else
    /usr/bin/open -n "$APP_BUNDLE"
  fi
}

case "$MODE" in
  --build|build)
    ;;
  run)
    open_app
    ;;
  --debug|debug)
    lldb -- "$APP_BINARY"
    ;;
  --logs|logs)
    open_app
    /usr/bin/log stream --info --style compact --predicate "process == \"$APP_EXECUTABLE_NAME\""
    ;;
  --telemetry|telemetry)
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"$BUNDLE_ID\""
    ;;
  --verify|verify)
    /usr/bin/xattr -cr "$APP_BUNDLE" 2>/dev/null || true
    "$ROOT_DIR/script/verify_app_bundle.sh" "$APP_BUNDLE"
    open_app
    sleep 2
    pgrep -x "$APP_EXECUTABLE_NAME" >/dev/null
    pkill -x "$APP_EXECUTABLE_NAME" >/dev/null 2>&1 || true
    wait_for_process_exit "$APP_EXECUTABLE_NAME" || pkill -9 -x "$APP_EXECUTABLE_NAME" >/dev/null 2>&1 || true
    /usr/bin/xattr -cr "$APP_BUNDLE" 2>/dev/null || true
    verify_clean_codesign "$APP_BUNDLE"
    ;;
  *)
    echo "usage: $0 [run|--build|--debug|--logs|--telemetry|--verify] [-- app-args...]" >&2
    exit 2
    ;;
esac
