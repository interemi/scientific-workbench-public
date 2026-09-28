#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DISPLAY_NAME="Scientific Workbench"
APP_BUNDLE="$ROOT_DIR/dist/$APP_DISPLAY_NAME.app"

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

cd "$ROOT_DIR"
"$ROOT_DIR/script/build_and_run.sh" --verify >/dev/null
if rg -n "advancedMode|Show advanced controls|Browse 53|53 user-facing capabilities" Sources Tests >/dev/null; then
  echo "ui smoke failed: stale Settings/control or hardcoded capability-count text found" >&2
  rg -n "advancedMode|Show advanced controls|Browse 53|53 user-facing capabilities" Sources Tests >&2
  exit 1
fi

cleanup() {
  pkill -TERM -x "$APP_DISPLAY_NAME" >/dev/null 2>&1 || true
  sleep 0.5
  pkill -KILL -x "$APP_DISPLAY_NAME" >/dev/null 2>&1 || true
  /usr/bin/xattr -cr "$APP_BUNDLE" 2>/dev/null || true
}
trap cleanup EXIT

cleanup
for _ in {1..20}; do
  if ! pgrep -x "$APP_DISPLAY_NAME" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

/usr/bin/open -n "$APP_BUNDLE"
app_pid_count=0
for _ in {1..40}; do
  app_pid_count="$(pgrep -x "$APP_DISPLAY_NAME" 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "$app_pid_count" -eq 1 ]]; then
    break
  fi
  sleep 0.25
done
if [[ "$app_pid_count" -ne 1 ]]; then
  echo "ui smoke failed: expected one $APP_DISPLAY_NAME process, found $app_pid_count" >&2
  exit 1
fi

run_with_timeout 60 /usr/bin/osascript <<'APPLESCRIPT'
on fail(message)
  error "ui smoke failed: " & message
end fail

on waitForMainWindow(appName, timeoutSeconds)
  set deadline to (current date) + timeoutSeconds
  repeat while (current date) < deadline
    try
      tell application "System Events"
        if exists process appName then
          tell process appName
            if (count of windows) > 0 then
              set frontmost to true
              return true
            end if
          end tell
        end if
      end tell
    end try
    delay 0.25
  end repeat
  my fail("main window did not appear")
end waitForMainWindow

on rootStaticTextExists(appName, targetText)
  try
    tell application "System Events"
      if not (exists process appName) then return false
      tell process appName
        if (count of windows) is 0 then return false
        tell window 1
          if not (exists group 1) then return false
          tell group 1
            repeat with textRef in static texts
              try
                if (name of textRef as text) is targetText then return true
              end try
            end repeat
          end tell
        end tell
      end tell
    end tell
  end try
  return false
end rootStaticTextExists

on waitForRootStaticText(appName, targetText, timeoutSeconds)
  set deadline to (current date) + timeoutSeconds
  repeat while (current date) < deadline
    if my rootStaticTextExists(appName, targetText) then return true
    delay 0.25
  end repeat
  my fail("root title text did not appear: " & targetText)
end waitForRootStaticText

on elementTreeContainsStaticText(elementRef, targetName)
  tell application "System Events"
    try
      if ((role of elementRef) as text) is "AXStaticText" then
        try
          if ((name of elementRef) as text) is targetName then return true
        end try
      end if
    end try
    try
      set childRefs to UI elements of elementRef
      repeat with childRef in childRefs
        try
          if my elementTreeContainsStaticText(childRef, targetName) then return true
        end try
      end repeat
    end try
  end tell
  return false
end elementTreeContainsStaticText

on elementTreeContainsSlider(elementRef)
  tell application "System Events"
    try
      set roleText to ((role of elementRef) as text)
      if roleText is "AXSlider" or roleText is "AXValueIndicator" then return true
    end try
    try
      set childRefs to UI elements of elementRef
      repeat with childRef in childRefs
        try
          if my elementTreeContainsSlider(childRef) then return true
        end try
      end repeat
    end try
  end tell
  return false
end elementTreeContainsSlider

on settingsStaticTextExists(appName, targetName)
  try
    tell application "System Events"
      if not (exists process appName) then return false
      tell process appName
        if (count of windows) is 0 then return false
        tell window 1
          if not (exists group 1) then return false
          tell group 1
            if my elementTreeContainsStaticText(it, targetName) then return true
          end tell
        end tell
      end tell
    end tell
  end try
  return false
end settingsStaticTextExists

on settingsSliderExists(appName)
  try
    tell application "System Events"
      if not (exists process appName) then return false
      tell process appName
        if (count of windows) is 0 then return false
        tell window 1
          if not (exists group 1) then return false
          tell group 1
            if my elementTreeContainsSlider(it) then return true
          end tell
        end tell
      end tell
    end tell
  end try
  return false
end settingsSliderExists

on scrollSettingsContent(appName, actionName)
  try
    tell application "System Events"
      if not (exists process appName) then return false
      tell process appName
        if (count of windows) is 0 then return false
        tell window 1
          if not (exists group 1) then return false
          tell group 1
            if (count of scroll areas) < 2 then return false
            tell scroll area 2
              perform action actionName
              return true
            end tell
          end tell
        end tell
      end tell
    end tell
  end try
  return false
end scrollSettingsContent

on resetSettingsScroll(appName)
  repeat 4 times
    my scrollSettingsContent(appName, "AXScrollUpByPage")
    delay 0.1
  end repeat
end resetSettingsScroll

on waitForSettingsStaticText(appName, targetName, timeoutSeconds)
  set deadline to (current date) + timeoutSeconds
  repeat while (current date) < deadline
    if my settingsStaticTextExists(appName, targetName) then return true
    my scrollSettingsContent(appName, "AXScrollDownByPage")
    delay 0.25
  end repeat
  my fail("capability timeout slider label is missing")
end waitForSettingsStaticText

on waitForSettingsSlider(appName, timeoutSeconds)
  set deadline to (current date) + timeoutSeconds
  repeat while (current date) < deadline
    if my settingsSliderExists(appName) then return true
    my scrollSettingsContent(appName, "AXScrollDownByPage")
    delay 0.25
  end repeat
  my fail("capability timeout slider is missing")
end waitForSettingsSlider

on clickElementWithIdentifier(elementRef, targetIdentifier)
  tell application "System Events"
    try
      set identifierValue to value of attribute "AXIdentifier" of elementRef
      if (identifierValue as text) is targetIdentifier then
        click elementRef
        return true
      end if
    end try
    try
      set childRefs to UI elements of elementRef
      repeat with childRef in childRefs
        try
          if my clickElementWithIdentifier(childRef, targetIdentifier) then return true
        end try
      end repeat
    end try
  end tell
  return false
end clickElementWithIdentifier

on clickSidebarButton(appName, sectionIdentifier)
  set deadline to (current date) + 8
  repeat while (current date) < deadline
    try
      tell application "System Events"
        if exists process appName then
          tell process appName
            if (count of windows) > 0 then
              tell window 1
                if exists group 1 then
                  tell group 1
                    if my clickElementWithIdentifier(it, sectionIdentifier) then return true
                  end tell
                end if
              end tell
            end if
          end tell
        end if
      end tell
    end try
    delay 0.25
  end repeat
  my fail("sidebar control " & sectionIdentifier & " is missing or not clickable")
end clickSidebarButton

set appName to "Scientific Workbench"
my waitForMainWindow(appName, 12)

my clickSidebarButton(appName, "sidebar.section.agent")
my waitForRootStaticText(appName, "Chat", 12)

my clickSidebarButton(appName, "sidebar.section.home")
my waitForRootStaticText(appName, "Dashboard", 12)

my clickSidebarButton(appName, "sidebar.section.capabilities")
my waitForRootStaticText(appName, "Capabilities", 12)

my clickSidebarButton(appName, "sidebar.section.jobs")
my waitForRootStaticText(appName, "Jobs", 12)

my clickSidebarButton(appName, "sidebar.section.results")
my waitForRootStaticText(appName, "Results", 12)

my clickSidebarButton(appName, "sidebar.section.maintenance")
my waitForRootStaticText(appName, "Maintenance", 12)

my clickSidebarButton(appName, "sidebar.section.settings")
my waitForRootStaticText(appName, "Settings", 12)
APPLESCRIPT

echo "Scientific Workbench UI smoke passed."
