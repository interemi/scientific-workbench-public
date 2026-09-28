#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DISPLAY_NAME="Scientific Workbench"
EXPECTED_BUNDLE_ID="com.emilio.scientific-workbench"
APP_BUNDLE="${1:-$ROOT_DIR/dist/$APP_DISPLAY_NAME.app}"
INFO_PLIST="$APP_BUNDLE/Contents/Info.plist"
APP_ICON="$APP_BUNDLE/Contents/Resources/AppIcon.icns"

fail() {
  echo "finder/dock smoke failed: $*" >&2
  exit 1
}

run_with_timeout() {
  local timeout_seconds="$1"
  shift

  "$@" &
  local command_pid="$!"
  local started_at="$SECONDS"

  while kill -0 "$command_pid" >/dev/null 2>&1; do
    if (( SECONDS - started_at >= timeout_seconds )); then
      kill "$command_pid" >/dev/null 2>&1 || true
      sleep 0.5
      kill -9 "$command_pid" >/dev/null 2>&1 || true
      wait "$command_pid" >/dev/null 2>&1 || true
      return 124
    fi
    sleep 0.2
  done

  wait "$command_pid"
}

plist_value() {
  /usr/libexec/PlistBuddy -c "Print :$1" "$INFO_PLIST" 2>/dev/null || true
}

cleanup() {
  pkill -TERM -x "$APP_DISPLAY_NAME" >/dev/null 2>&1 || true
  sleep 0.5
  pkill -KILL -x "$APP_DISPLAY_NAME" >/dev/null 2>&1 || true
  /usr/bin/xattr -cr "$APP_BUNDLE" 2>/dev/null || true
}
trap cleanup EXIT

cd "$ROOT_DIR"
if [[ ! -d "$APP_BUNDLE" ]]; then
  "$ROOT_DIR/script/build_and_run.sh" --build >/dev/null
fi

[[ -d "$APP_BUNDLE" ]] || fail "missing app bundle at $APP_BUNDLE"
[[ -f "$INFO_PLIST" ]] || fail "missing Info.plist"
[[ -f "$APP_ICON" ]] || fail "missing AppIcon.icns"
[[ "$(plist_value CFBundleIdentifier)" == "$EXPECTED_BUNDLE_ID" ]] || fail "unexpected CFBundleIdentifier"
[[ "$(plist_value CFBundlePackageType)" == "APPL" ]] || fail "unexpected CFBundlePackageType"
[[ "$(plist_value CFBundleDisplayName)" == "$APP_DISPLAY_NAME" ]] || fail "unexpected CFBundleDisplayName"
[[ "$(plist_value CFBundleIconFile)" == "AppIcon" ]] || fail "unexpected CFBundleIconFile"
[[ -z "$(plist_value LSUIElement)" ]] || fail "LSUIElement must not be set; app should appear in Dock"
[[ -z "$(plist_value LSBackgroundOnly)" ]] || fail "LSBackgroundOnly must not be set; app should be foreground-capable"
[[ -s "$APP_ICON" ]] || fail "AppIcon.icns is empty"

cleanup
for _ in {1..30}; do
  if ! pgrep -x "$APP_DISPLAY_NAME" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

/usr/bin/open -n "$APP_BUNDLE"

app_pid_count=0
for _ in {1..50}; do
  app_pid_count="$(pgrep -x "$APP_DISPLAY_NAME" 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$app_pid_count" -eq 1 ]]; then
    break
  fi
  sleep 0.25
done
[[ "$app_pid_count" -eq 1 ]] || fail "expected one $APP_DISPLAY_NAME process, found $app_pid_count"

reported_bundle_id="$(run_with_timeout 8 /usr/bin/osascript -e "id of application \"$APP_DISPLAY_NAME\"" 2>/dev/null || true)"
[[ "$reported_bundle_id" == "$EXPECTED_BUNDLE_ID" ]] || fail "LaunchServices reported bundle id '$reported_bundle_id'"

run_with_timeout 25 /usr/bin/osascript <<'APPLESCRIPT'
on fail(message)
  error "finder/dock smoke failed: " & message
end fail

on dockTileExists(appName)
  tell application "System Events"
    if not (exists process "Dock") then return false
    tell process "Dock"
      repeat with dockList in lists
        repeat with dockItem in UI elements of dockList
          try
            if (name of dockItem as text) is appName then return true
          end try
        end repeat
      end repeat
    end tell
  end tell
  return false
end dockTileExists

on waitForVisibleWindow(appName, timeoutSeconds)
  set deadline to (current date) + timeoutSeconds
  repeat while (current date) < deadline
    tell application "System Events"
      if exists process appName then
        tell process appName
          if (count of windows) > 0 then return true
        end tell
      end if
    end tell
    delay 0.25
  end repeat
  my fail("app did not expose a visible window")
end waitForVisibleWindow

on waitForDockTile(appName, timeoutSeconds)
  set deadline to (current date) + timeoutSeconds
  repeat while (current date) < deadline
    if my dockTileExists(appName) then return true
    delay 0.25
  end repeat
  my fail("Dock did not expose a running tile named " & appName)
end waitForDockTile

set appName to "Scientific Workbench"
my waitForVisibleWindow(appName, 12)
my waitForDockTile(appName, 12)
APPLESCRIPT

echo "Scientific Workbench Finder/Dock smoke passed."
