#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TESTS_DIR="$ROOT_DIR/Tests/ScientificWorkbenchTests"
RUNNER_DIR="${SCIENTIFIC_WORKBENCH_SWIFT_TEST_RUNNER_DIR:-$ROOT_DIR/.build/scientific-workbench-swift-testing-runner}"
SWIFT_OPTIONS=(--package-path "$ROOT_DIR")
if [[ -n "${SCIENTIFIC_WORKBENCH_SWIFT_BUILD_SYSTEM:-}" ]]; then
  SWIFT_OPTIONS+=(--build-system "$SCIENTIFIC_WORKBENCH_SWIFT_BUILD_SYSTEM")
fi
if [[ -n "${SCIENTIFIC_WORKBENCH_SWIFT_SCRATCH_PATH:-}" ]]; then
  SWIFT_OPTIONS+=(--scratch-path "$SCIENTIFIC_WORKBENCH_SWIFT_SCRATCH_PATH")
fi

cd "$ROOT_DIR"

fail() {
  echo "swift test runner failed: $*" >&2
  exit 1
}

testing_framework_dir() {
  local candidate
  for candidate in \
    "${DEVELOPER_DIR:-}" \
    "/Library/Developer/CommandLineTools" \
    "/Applications/Xcode.app/Contents/Developer" \
    "/Applications/Xcode-beta.app/Contents/Developer"; do
    [[ -n "$candidate" ]] || continue
    if [[ -d "$candidate/Library/Developer/Frameworks/Testing.framework" ]]; then
      printf '%s\n' "$candidate/Library/Developer/Frameworks"
      return 0
    fi
  done
  return 1
}

testing_interop_dir() {
  local candidate
  for candidate in \
    "${DEVELOPER_DIR:-}" \
    "/Library/Developer/CommandLineTools" \
    "/Applications/Xcode.app/Contents/Developer" \
    "/Applications/Xcode-beta.app/Contents/Developer"; do
    [[ -n "$candidate" ]] || continue
    if [[ -f "$candidate/Library/Developer/usr/lib/lib_TestingInterop.dylib" ]]; then
      printf '%s\n' "$candidate/Library/Developer/usr/lib"
      return 0
    fi
  done
  return 1
}

testing_plugin_dir() {
  local candidate
  for candidate in \
    "${DEVELOPER_DIR:-}" \
    "/Library/Developer/CommandLineTools" \
    "/Applications/Xcode.app/Contents/Developer" \
    "/Applications/Xcode-beta.app/Contents/Developer"; do
    [[ -n "$candidate" ]] || continue
    if [[ -d "$candidate/usr/lib/swift/host/plugins/testing" ]]; then
      printf '%s\n' "$candidate/usr/lib/swift/host/plugins/testing"
      return 0
    fi
  done
  return 1
}

normalize_runner_args() {
  /usr/bin/python3 - "$@" <<'PY'
import sys

args = sys.argv[1:]
for index, arg in enumerate(args[:-1]):
    if arg == "--filter" and "/" in args[index + 1]:
        args[index + 1] = args[index + 1].split("/")[-1]
if args:
    sys.stdout.buffer.write("\0".join(args).encode("utf-8") + b"\0")
PY
}

expected_test_count() {
  /usr/bin/python3 - "$TESTS_DIR" <<'PY'
import pathlib
import re
import sys

tests_root = pathlib.Path(sys.argv[1])
count = 0
for path in sorted(tests_root.glob("*.swift")):
    count += len(re.findall(r"(?m)^\s*@Test\b", path.read_text(encoding="utf-8")))
print(count)
PY
}

summary_test_count() {
  /usr/bin/python3 - "$1" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
matches = re.findall(r"Test run with (\d+) tests?\b", text)
if not matches:
    raise SystemExit(1)
print(matches[-1])
PY
}

EXPECTED_COUNT="$(expected_test_count)"

mkdir -p "$RUNNER_DIR"
echo "Swift toolchain:"
swift --version | sed 's/^/  /'
echo "Developer directory: $(xcode-select -p)"
echo "Expected Swift Testing tests in target: $EXPECTED_COUNT"

# Use SwiftPM's supported runner where discovery works (including Xcode CI).
# A failing build/test must never be hidden by a successful fallback run.
NATIVE_LOG_PATH="$RUNNER_DIR/native-output.log"
set +e
swift test "${SWIFT_OPTIONS[@]}" --enable-swift-testing --disable-xctest "$@" 2>&1 | tee "$NATIVE_LOG_PATH"
native_status="${PIPESTATUS[0]}"
set -e
[[ "$native_status" -eq 0 ]] || exit "$native_status"
NATIVE_COUNT="$(summary_test_count "$NATIVE_LOG_PATH" || printf '0')"
if [[ "$NATIVE_COUNT" -gt 0 ]]; then
  if [[ "$#" -eq 0 && "$NATIVE_COUNT" -lt "$EXPECTED_COUNT" ]]; then
    fail "SwiftPM executed $NATIVE_COUNT tests, expected at least $EXPECTED_COUNT"
  fi
  echo "Executed Swift Testing tests: $NATIVE_COUNT (SwiftPM)"
  exit 0
fi

echo "SwiftPM reported no Swift Testing tests; trying the Command Line Tools fallback."
TESTING_FRAMEWORK_DIR="$(testing_framework_dir)" || fail "could not locate Testing.framework"
TESTING_INTEROP_DIR="$(testing_interop_dir)" || fail "could not locate lib_TestingInterop.dylib"
TESTING_PLUGIN_DIR="$(testing_plugin_dir)" || fail "could not locate Swift Testing macro plugin"
SDK_PATH="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path)}" || fail "could not locate macOS SDK"
ARCH="$(uname -m)"

cat > "$RUNNER_DIR/runner.swift" <<'SWIFT'
import Testing

@main
struct ScientificWorkbenchSwiftTestingRunner {
  static func main() async {
    await Testing.__swiftPMEntryPoint() as Never
  }
}
SWIFT

BUILD_DIR="$(swift build "${SWIFT_OPTIONS[@]}" --show-bin-path)"
LINK_FILE_LIST="$BUILD_DIR/ScientificWorkbenchPackageTests.product/Objects.LinkFileList"
[[ -f "$LINK_FILE_LIST" ]] || fail "missing SwiftPM link file list at $LINK_FILE_LIST"

objects=()
while IFS= read -r line; do
  object="${line#\'}"
  object="${object%\'}"
  case "$object" in
    *ScientificWorkbenchApp.swift.o|*ScientificWorkbenchMain.swift.o|*ScientificWorkbenchPackageTests.build/runner.swift.o)
      ;;
    *)
      objects+=("$object")
      ;;
  esac
done < "$LINK_FILE_LIST"

[[ "${#objects[@]}" -gt 0 ]] || fail "no SwiftPM objects found for explicit test runner"

swiftc \
  -parse-as-library \
  -swift-version 6 \
  -target "$ARCH-apple-macosx14.0" \
  -sdk "$SDK_PATH" \
  -enable-testing \
  -D SWIFT_PACKAGE \
  -D DEBUG \
  -I "$BUILD_DIR/Modules" \
  -I "$TESTING_FRAMEWORK_DIR" \
  -F "$TESTING_FRAMEWORK_DIR" \
  -plugin-path "$TESTING_PLUGIN_DIR" \
  -Xlinker -rpath -Xlinker "$TESTING_FRAMEWORK_DIR" \
  -Xlinker -rpath -Xlinker "$TESTING_INTEROP_DIR" \
  "$RUNNER_DIR/runner.swift" \
  "${objects[@]}" \
  -o "$RUNNER_DIR/ScientificWorkbenchSwiftTestingRunner"

runner_args=()
if [[ "$#" -gt 0 ]]; then
  while IFS= read -r -d '' arg; do
    runner_args+=("$arg")
  done < <(normalize_runner_args "$@")
fi

LOG_PATH="$RUNNER_DIR/latest-output.log"
set +e
if [[ "${#runner_args[@]}" -gt 0 ]]; then
  "$RUNNER_DIR/ScientificWorkbenchSwiftTestingRunner" "${runner_args[@]}" 2>&1 | tee "$LOG_PATH"
else
  "$RUNNER_DIR/ScientificWorkbenchSwiftTestingRunner" 2>&1 | tee "$LOG_PATH"
fi
test_status="${PIPESTATUS[0]}"
set -e

EXECUTED_COUNT="$(summary_test_count "$LOG_PATH")" || fail "Swift Testing summary was not emitted"
echo "Executed Swift Testing tests: $EXECUTED_COUNT"
[[ "$EXECUTED_COUNT" -gt 0 ]] || fail "no tests matched; zero tests is not a passing validation"

if [[ "$#" -eq 0 && "$EXECUTED_COUNT" -lt "$EXPECTED_COUNT" ]]; then
  fail "executed $EXECUTED_COUNT tests, expected at least $EXPECTED_COUNT from $TESTS_DIR"
fi

exit "$test_status"
