#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DISPLAY_NAME="Scientific Workbench"
APP_BUNDLE="$ROOT_DIR/dist/$APP_DISPLAY_NAME.app"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientificworkbench-first-run.XXXXXX")"
KEEP_FIRST_RUN_SMOKE="${KEEP_FIRST_RUN_SMOKE:-0}"

cleanup() {
  /usr/bin/osascript -e "tell application \"$APP_DISPLAY_NAME\" to quit" >/dev/null 2>&1 || true
  pkill -x "$APP_DISPLAY_NAME" >/dev/null 2>&1 || true
  /usr/bin/xattr -cr "$APP_BUNDLE" 2>/dev/null || true
  if [[ "$KEEP_FIRST_RUN_SMOKE" != "1" ]]; then
    rm -rf "$TMP_ROOT"
  else
    echo "kept first-run smoke files at $TMP_ROOT"
  fi
}
trap cleanup EXIT

cd "$ROOT_DIR"
"$ROOT_DIR/script/build_and_run.sh" --build >/dev/null

INPUT_ROOT="$TMP_ROOT/input"
OUTPUT_ROOT="$TMP_ROOT/output"
TRANSCRIPT="$OUTPUT_ROOT/transcript.json"
mkdir -p "$INPUT_ROOT" "$OUTPUT_ROOT"
cat >"$INPUT_ROOT/table.csv" <<'CSV'
time,flux
1,2
2,3
CSV
cat >"$INPUT_ROOT/notes.md" <<'MD'
# First-run smoke

This fixture must remain unchanged.
MD

INPUT_HASH_BEFORE="$(find "$INPUT_ROOT" -type f -print0 | sort -z | xargs -0 /usr/bin/shasum -a 256)"

/usr/bin/open -n "$APP_BUNDLE" --args \
  --agent-input "$INPUT_ROOT" \
  --agent-mode workflow \
  --agent-local-planner \
  --agent-output-root "$OUTPUT_ROOT" \
  --agent-prompt "Fresh first-run smoke: plan a safe local analysis without editing originals." \
  --agent-transcript-json "$TRANSCRIPT" \
  --agent-isolated-session \
  --agent-exit-after-run

for _ in {1..100}; do
  [[ -f "$TRANSCRIPT" ]] && break
  sleep 0.25
done
[[ -f "$TRANSCRIPT" ]] || {
  echo "first-run smoke failed: isolated packaged launch did not write transcript" >&2
  exit 1
}

INPUT_HASH_AFTER="$(find "$INPUT_ROOT" -type f -print0 | sort -z | xargs -0 /usr/bin/shasum -a 256)"
if [[ "$INPUT_HASH_BEFORE" != "$INPUT_HASH_AFTER" ]]; then
  echo "first-run smoke failed: input fixture changed during first-run planning" >&2
  diff <(printf "%s\n" "$INPUT_HASH_BEFORE") <(printf "%s\n" "$INPUT_HASH_AFTER") >&2 || true
  exit 1
fi

/usr/bin/python3 - "$TRANSCRIPT" "$INPUT_ROOT" "$OUTPUT_ROOT" <<'PY'
import json
import os
import sys

transcript_path, input_root, output_root = sys.argv[1:4]
input_root = os.path.realpath(input_root)
output_root = os.path.realpath(output_root)
with open(transcript_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

def fail(message: str) -> None:
    raise SystemExit(f"first-run smoke failed: {message}")

if payload.get("agent_mode") != "workflow":
    fail(f"unexpected agent_mode: {payload.get('agent_mode')!r}")
if payload.get("ai_provider") != "ollama":
    fail(f"fresh isolated session should default to ollama, got {payload.get('ai_provider')!r}")
if payload.get("auto_run") is not False:
    fail("fresh first-run smoke should plan only")
if os.path.realpath(payload.get("output_root", "")) != output_root:
    fail("transcript output_root mismatch")
input_paths = [os.path.realpath(path) for path in payload.get("input_paths", [])]
if input_root not in input_paths:
    fail("transcript is missing isolated input path")

checklist = payload.get("setup_checklist")
if not isinstance(checklist, list) or not checklist:
    fail("missing setup_checklist")
by_id = {item.get("id"): item for item in checklist if isinstance(item, dict)}
required_ids = ["environment", "capabilities", "output_root", "local_ai"]
missing = [item_id for item_id in required_ids if item_id not in by_id]
if missing:
    fail(f"missing required setup items: {missing}")

for item_id in required_ids:
    item = by_id[item_id]
    if item.get("is_required") is not True:
        fail(f"{item_id} should be marked required")
    if item.get("state") not in {"ready", "action"}:
        fail(f"{item_id} has unexpected state {item.get('state')!r}")
    if not item.get("detail"):
        fail(f"{item_id} has empty detail")

if by_id["output_root"].get("state") != "ready":
    fail("output_root should be ready after launch automation creates the isolated output folder")

blocked = [
    item_id for item_id in required_ids
    if by_id[item_id].get("state") != "ready"
]
recovery = payload.get("setup_recovery")
if blocked:
    if not isinstance(recovery, dict):
        fail(f"blocked setup items {blocked} should include setup_recovery")
    blocking_ids = recovery.get("blocking_item_ids")
    if not isinstance(blocking_ids, list) or sorted(blocking_ids) != sorted(blocked):
        fail(f"setup_recovery blocking ids mismatch: {blocking_ids!r} != {blocked!r}")
    actions = recovery.get("recommended_actions")
    if not isinstance(actions, list) or not actions:
        fail("setup_recovery should include recommended actions")
else:
    if recovery is not None:
        fail("setup_recovery should be null when required setup is ready")

plan = payload.get("agent_plan")
if not isinstance(plan, dict):
    fail("missing structured agent_plan")
if plan.get("source") not in {"local", "skillRouter"}:
    fail(f"expected local or skillRouter planner, got {plan.get('source')!r}")
steps = plan.get("steps")
if not isinstance(steps, list) or not steps:
    fail("missing plan steps")
ids = [step.get("capability_id") for step in steps if isinstance(step, dict)]
if plan.get("source") == "skillRouter":
    required_steps = {"cross_domain_data_workbench", "document_intake_workbench"}
else:
    required_steps = {"profile_table"}
missing_steps = sorted(required_steps.difference(ids))
if missing_steps:
    fail(f"missing expected first-run capabilities {missing_steps}; got {ids}")

if payload.get("jobs") not in ([], None):
    fail("first-run smoke should not auto-run jobs")

print("Scientific Workbench first-run smoke passed.")
PY
