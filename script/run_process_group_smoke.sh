#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${TMPDIR:-/tmp}/Scientific-Workbench-ProcessGroup-Smoke"
REPORT_PATH="$REPORT_DIR/report.json"

cd "$ROOT_DIR"
mkdir -p "$REPORT_DIR"
rm -f "$REPORT_PATH"

swift build >/dev/null
"$ROOT_DIR/.build/debug/ScientificWorkbench" \
  --process-group-smoke \
  "$ROOT_DIR/Tests/Fixtures/process_tree_fixture.py" \
  "$REPORT_PATH"

python3 - "$REPORT_PATH" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
report = json.loads(path.read_text(encoding="utf-8"))
if report.get("passed") is not True:
    raise SystemExit("process-group smoke reported failure")

cancel = report["cancellation"]
timeout = report["timeout"]
if cancel.get("unrelatedProcessSurvived") is not True:
    raise SystemExit("unrelated process did not survive cancellation")
if cancel.get("treeExited") is not True or timeout.get("treeExited") is not True:
    raise SystemExit("a process tree survived cancellation or timeout")
if not timeout.get("outcome", "").startswith("timed_out_after="):
    raise SystemExit("timeout scenario did not report ProcessRunnerError.timedOut")

print(f"Process-group smoke passed: {path}")
for name in ("cancellation", "timeout"):
    scenario = report[name]
    if scenario["processGroupID"] != scenario["parentPID"]:
        raise SystemExit(f"{name} did not run in a dedicated process group")
    print(
        f"{name}: pgid={scenario['processGroupID']} "
        f"pids={scenario['parentPID']},{scenario['childPID']},{scenario['grandchildPID']} "
        f"outcome={scenario['outcome']}"
    )
    for row in scenario["processSnapshot"]:
        print(f"  ps: {row}")
PY
