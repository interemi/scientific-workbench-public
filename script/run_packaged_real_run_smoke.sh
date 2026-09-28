#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DISPLAY_NAME="Scientific Workbench"
APP_BUNDLE="$ROOT_DIR/dist/$APP_DISPLAY_NAME.app"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientificworkbench-packaged-real-run.XXXXXX")"
KEEP_PACKAGED_REAL_RUN="${KEEP_PACKAGED_REAL_RUN:-0}"

cleanup() {
  /usr/bin/osascript -e "tell application \"$APP_DISPLAY_NAME\" to quit" >/dev/null 2>&1 || true
  pkill -x "$APP_DISPLAY_NAME" >/dev/null 2>&1 || true
  /usr/bin/xattr -cr "$APP_BUNDLE" 2>/dev/null || true
  if [[ "$KEEP_PACKAGED_REAL_RUN" != "1" ]]; then
    rm -rf "$TMP_ROOT"
  else
    echo "kept packaged real-run smoke files at $TMP_ROOT"
  fi
}
trap cleanup EXIT

cd "$ROOT_DIR"
"$ROOT_DIR/script/build_and_run.sh" --build >/dev/null

INPUT_ROOT="$TMP_ROOT/input"
OUTPUT_ROOT="$TMP_ROOT/output"
TRANSCRIPT="$OUTPUT_ROOT/transcript.json"
FINGERPRINT_BEFORE="$OUTPUT_ROOT/input_fingerprint_before.json"
FINGERPRINT_AFTER="$OUTPUT_ROOT/input_fingerprint_after.json"

mkdir -p "$INPUT_ROOT" "$OUTPUT_ROOT"
cat >"$INPUT_ROOT/table.csv" <<'CSV'
time,flux,error
1,2.4,0.1
2,2.9,0.1
3,3.3,0.2
CSV

fingerprint_inputs() {
  local output_json="$1"
  local input_root="$2"
  /usr/bin/python3 - "$output_json" "$input_root" <<'PY'
import hashlib
import json
import os
import sys

output_json, input_root = sys.argv[1:3]
fingerprint = {}
for directory, _, filenames in os.walk(input_root):
    for filename in sorted(filenames):
        path = os.path.join(directory, filename)
        rel = os.path.relpath(path, input_root)
        with open(path, "rb") as handle:
            fingerprint[rel] = hashlib.sha256(handle.read()).hexdigest()
with open(output_json, "w", encoding="utf-8") as handle:
    json.dump(fingerprint, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
}

fingerprint_inputs "$FINGERPRINT_BEFORE" "$INPUT_ROOT"

/usr/bin/open -n "$APP_BUNDLE" --args \
  --agent-input "$INPUT_ROOT/table.csv" \
  --agent-mode workflow \
  --agent-local-planner \
  --agent-auto-run \
  --agent-output-root "$OUTPUT_ROOT" \
  --agent-prompt "Packaged real-run smoke: profile this CSV table and write outputs without editing the original." \
  --agent-transcript-json "$TRANSCRIPT" \
  --agent-isolated-session \
  --agent-exit-after-run

for _ in {1..160}; do
  [[ -f "$TRANSCRIPT" ]] && break
  sleep 0.25
done
[[ -f "$TRANSCRIPT" ]] || {
  echo "packaged real-run smoke failed: app did not write transcript" >&2
  exit 1
}

fingerprint_inputs "$FINGERPRINT_AFTER" "$INPUT_ROOT"

/usr/bin/python3 - "$TRANSCRIPT" "$OUTPUT_ROOT" "$FINGERPRINT_BEFORE" "$FINGERPRINT_AFTER" <<'PY'
import json
import os
import sys

transcript_path, output_root, before_path, after_path = sys.argv[1:5]
output_root = os.path.realpath(output_root)

with open(before_path, "r", encoding="utf-8") as handle:
    before = json.load(handle)
with open(after_path, "r", encoding="utf-8") as handle:
    after = json.load(handle)
if before != after:
    raise SystemExit("packaged real-run smoke failed: input fixture changed")

with open(transcript_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

def fail(message: str) -> None:
    raise SystemExit(f"packaged real-run smoke failed: {message}")

if payload.get("agent_mode") != "workflow":
    fail(f"unexpected agent_mode: {payload.get('agent_mode')!r}")
if payload.get("auto_run") is not True:
    fail("expected auto_run true")
if os.path.realpath(payload.get("output_root", "")) != output_root:
    fail("transcript output_root mismatch")

plan = payload.get("agent_plan")
if not isinstance(plan, dict):
    fail("missing structured agent_plan")
if plan.get("source") not in {"local", "skillRouter"}:
    fail(f"expected local or skillRouter planner, got {plan.get('source')!r}")
steps = plan.get("steps")
if not isinstance(steps, list) or not steps:
    fail("missing plan steps")
enabled_step_ids = [step.get("capability_id") for step in steps if step.get("is_enabled", True)]
for expected in ["datanalysis_env.status", "profile_table"]:
    if expected not in enabled_step_ids:
        fail(f"missing expected enabled step {expected}; got {enabled_step_ids}")

jobs = payload.get("jobs")
if not isinstance(jobs, list):
    fail("missing jobs list")
scoped_jobs = []
for job in jobs:
    run_directory = job.get("run_directory")
    if not isinstance(run_directory, str):
        continue
    real_run = os.path.realpath(run_directory)
    if real_run == output_root or real_run.startswith(output_root + os.sep):
        scoped_jobs.append(job)
if not scoped_jobs:
    fail("no jobs executed inside output root")

job_ids = [job.get("capability_id") for job in scoped_jobs]
for expected in ["datanalysis_env.status", "profile_table"]:
    if expected not in job_ids:
        fail(f"missing expected job {expected}; got {job_ids}")

bad_jobs = [job for job in scoped_jobs if job.get("status") != "succeeded"]
if bad_jobs:
    details = [f"{job.get('capability_id')}={job.get('status')} exit={job.get('exit_code')}" for job in bad_jobs]
    fail(f"expected all jobs to succeed; {details}")

artifact_count = 0
for job in scoped_jobs:
    run_directory = job.get("run_directory")
    capability_id = job.get("capability_id")
    artifacts = job.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        fail(f"job has no artifacts: {capability_id}")
    artifact_count += len(artifacts)
    summary_path = os.path.join(run_directory, "summary.json")
    if not os.path.isfile(summary_path):
        fail(f"missing summary.json for {capability_id}")
    for sidecar in ["stdout.txt", "stderr.txt", "command.txt", "next_steps.md"]:
        if not os.path.isfile(os.path.join(run_directory, sidecar)):
            fail(f"missing {sidecar} for {capability_id}")
    if capability_id == "profile_table":
        manifest_path = os.path.join(run_directory, "manifest.json")
        if not os.path.isfile(manifest_path):
            fail("missing manifest.json for profile_table")
        artifact_names = [
            artifact.get("relative_path", "")
            for artifact in artifacts
            if isinstance(artifact, dict)
        ]
        if not any(name.endswith(".csv") or name.endswith(".json") or name.endswith(".md") for name in artifact_names):
            fail(f"profile_table artifacts look incomplete: {artifact_names}")

summary_root = os.path.join(output_root, "Workflow Summaries")
if not os.path.isdir(summary_root):
    fail("missing Workflow Summaries directory")
summaries = sorted(name for name in os.listdir(summary_root) if name.endswith("_workflow_summary.md"))
if not summaries:
    fail("missing workflow summary markdown")
latest_summary = os.path.join(summary_root, summaries[-1])
with open(latest_summary, "r", encoding="utf-8") as handle:
    summary_text = handle.read()
for required in [
    "# Scientific Workbench Workflow Summary",
    "profile_table",
    "Read-Only Inputs",
    "original inputs as read-only",
]:
    if required not in summary_text:
        fail(f"workflow summary missing {required!r}")

if artifact_count < 2:
    fail(f"expected at least two artifacts, got {artifact_count}")

print(f"Scientific Workbench packaged real-run smoke passed: {len(scoped_jobs)} jobs, {artifact_count} artifacts.")
PY
