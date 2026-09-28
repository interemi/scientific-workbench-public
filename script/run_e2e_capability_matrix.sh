#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scientific-workbench-e2e.XXXXXX")"
KEEP_E2E_MATRIX="${KEEP_E2E_MATRIX:-0}"

cleanup() {
  if [[ "$KEEP_E2E_MATRIX" != "1" ]]; then
    rm -rf "$TMP_ROOT"
  else
    echo "kept E2E matrix files at $TMP_ROOT"
  fi
}
trap cleanup EXIT

cd "$ROOT_DIR"
swift build >/dev/null
APP_BINARY="$(swift build --show-bin-path)/ScientificWorkbench"

write_fixture_file() {
  local path="$1"
  local body="$2"
  mkdir -p "$(dirname "$path")"
  printf "%s" "$body" >"$path"
}

write_valid_fits_fixture() {
  local path="$1"
  mkdir -p "$(dirname "$path")"
  /usr/bin/python3 - "$path" <<'PY'
import struct
import sys
from pathlib import Path

path = Path(sys.argv[1])
cards = [
    "SIMPLE  =                    T",
    "BITPIX  =                   16",
    "NAXIS   =                    2",
    "NAXIS1  =                    2",
    "NAXIS2  =                    2",
    "EXTEND  =                    T",
    "OBJECT  = 'Synthetic 2x2'",
    "BUNIT   = 'adu     '",
    "END",
]
header = b"".join(card.ljust(80).encode("ascii") for card in cards)
header += b" " * ((2880 - (len(header) % 2880)) % 2880)
data = struct.pack(">4h", 100, 200, 300, 400)
data += b"\0" * ((2880 - (len(data) % 2880)) % 2880)
path.write_bytes(header + data)
PY
}

fingerprint_inputs() {
  local output_file="$1"
  shift
  /usr/bin/python3 - "$output_file" "$@" <<'PY'
import hashlib
import json
import os
import sys

output_file = sys.argv[1]
input_paths = sys.argv[2:]
records = []

def digest_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def add_record(path, input_root):
    real_path = os.path.realpath(path)
    if os.path.islink(path):
        records.append({
            "path": real_path,
            "input_root": os.path.realpath(input_root),
            "kind": "symlink",
            "target": os.readlink(path),
        })
    elif os.path.isdir(path):
        records.append({
            "path": real_path,
            "input_root": os.path.realpath(input_root),
            "kind": "directory",
        })
    elif os.path.isfile(path):
        stat_result = os.stat(path)
        records.append({
            "path": real_path,
            "input_root": os.path.realpath(input_root),
            "kind": "file",
            "size": stat_result.st_size,
            "sha256": digest_file(path),
        })
    else:
        records.append({
            "path": real_path,
            "input_root": os.path.realpath(input_root),
            "kind": "other",
        })

for input_path in input_paths:
    if not os.path.exists(input_path):
        records.append({
            "path": os.path.realpath(input_path),
            "input_root": os.path.realpath(input_path),
            "kind": "missing",
        })
        continue

    if os.path.isdir(input_path):
        add_record(input_path, input_path)
        for directory, dirnames, filenames in os.walk(input_path, followlinks=False):
            dirnames[:] = sorted(dirnames)
            for dirname in dirnames:
                add_record(os.path.join(directory, dirname), input_path)
            for filename in sorted(filenames):
                add_record(os.path.join(directory, filename), input_path)
    else:
        add_record(input_path, input_path)

records.sort(key=lambda item: (item["path"], item["kind"]))
with open(output_file, "w", encoding="utf-8") as handle:
    json.dump(records, handle, indent=2, sort_keys=True)
PY
}

validate_inputs_unchanged() {
  local before_file="$1"
  local after_file="$2"
  local case_name="$3"
  /usr/bin/python3 - "$before_file" "$after_file" "$case_name" <<'PY'
import json
import sys

before_path, after_path, case_name = sys.argv[1:4]
with open(before_path, "r", encoding="utf-8") as handle:
    before = json.load(handle)
with open(after_path, "r", encoding="utf-8") as handle:
    after = json.load(handle)

if before != after:
    before_map = {(item.get("path"), item.get("kind")): item for item in before}
    after_map = {(item.get("path"), item.get("kind")): item for item in after}
    removed = sorted(set(before_map) - set(after_map))
    added = sorted(set(after_map) - set(before_map))
    changed = sorted(
        key for key in set(before_map).intersection(after_map)
        if before_map[key] != after_map[key]
    )
    raise SystemExit(
        f"{case_name}: input fixtures changed; added={added[:5]} removed={removed[:5]} changed={changed[:5]}"
    )
PY
}

validate_transcript() {
  local transcript="$1"
  local case_name="$2"
  local output_root="$3"
  local expected_csv="$4"
  /usr/bin/python3 - "$transcript" "$case_name" "$output_root" "$expected_csv" <<'PY'
import json
import os
import sys

transcript_path = sys.argv[1]
case_name = sys.argv[2]
output_root = os.path.realpath(sys.argv[3])
expected = [item for item in sys.argv[4].split(",") if item]

with open(transcript_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

def normalized_status(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    aliases = {
        "OK": "PASS",
        "PASS": "PASS",
        "SUCCESS": "PASS",
        "SUCCEEDED": "PASS",
        "READY": "PASS",
        "WARNING": "WARNING",
        "WARN": "WARNING",
        "SKIP": "WARNING",
        "SKIPPED": "WARNING",
        "BLOCKED": "BLOCKED_CONTROLADO",
        "BLOCKED_CONTROLADO": "BLOCKED_CONTROLADO",
        "FAIL": "FAIL",
        "FAILED": "FAIL",
        "ERROR": "FAIL",
        "ROTO": "ROTO",
    }
    return aliases.get(normalized, normalized)

plan = payload.get("agent_plan")
if not isinstance(plan, dict):
    raise SystemExit(f"{case_name}: missing structured agent_plan")
if plan.get("source") not in {"local", "skillRouter"}:
    raise SystemExit(f"{case_name}: expected local or skillRouter planner, got {plan.get('source')!r}")

steps = plan.get("steps")
if not isinstance(steps, list) or not steps:
    raise SystemExit(f"{case_name}: missing plan steps")
all_step_ids = [step.get("capability_id") for step in steps]
maintainer_only = {
    "external_astro_tools_local_validation",
    "capability_probe_matrix",
    "portable_smoke_test",
    "validate_skill_samples",
    "sync_public_surface_docs",
    "skill_surface_audit",
}
leaked_maintainer = [capability for capability in all_step_ids if capability in maintainer_only]
if leaked_maintainer:
    raise SystemExit(f"{case_name}: maintainer-only capabilities leaked into the plan: {leaked_maintainer}")
if all_step_ids != expected:
    raise SystemExit(f"{case_name}: plan capabilities/order changed; expected {expected}, got {all_step_ids}")
step_ids = [step.get("capability_id") for step in steps if step.get("is_enabled", True)]
if step_ids != expected:
    raise SystemExit(f"{case_name}: expected every scenario step to be enabled; expected {expected}, got {step_ids}")

jobs = payload.get("jobs")
if not isinstance(jobs, list):
    raise SystemExit(f"{case_name}: missing jobs list")

scoped_jobs = []
for job in jobs:
    run_directory = job.get("run_directory")
    if not isinstance(run_directory, str):
        continue
    real_run = os.path.realpath(run_directory)
    if real_run == output_root or real_run.startswith(output_root + os.sep):
        scoped_jobs.append(job)

if not scoped_jobs:
    raise SystemExit(f"{case_name}: no jobs were executed inside {output_root}")

job_ids = [job.get("capability_id") for job in scoped_jobs]
if len(job_ids) != len(expected) or set(job_ids) != set(expected):
    raise SystemExit(f"{case_name}: executed jobs changed; expected exactly {expected}, got {job_ids}")

bad_jobs = [job for job in scoped_jobs if job.get("status") != "succeeded"]
if bad_jobs:
    details = [f"{job.get('capability_id')}={job.get('status')} exit={job.get('exit_code')}" for job in bad_jobs]
    raise SystemExit(f"{case_name}: expected all scoped jobs to succeed; {details}")

for job in scoped_jobs:
    capability_id = job.get("capability_id")
    run_directory = job.get("run_directory")
    if not os.path.isdir(run_directory):
        raise SystemExit(f"{case_name}: missing run directory for {capability_id}: {run_directory}")

    summary_path = os.path.join(run_directory, "summary.json")
    if not os.path.isfile(summary_path):
        raise SystemExit(f"{case_name}: missing summary.json for {capability_id}")
    with open(summary_path, "r", encoding="utf-8") as handle:
        summary = json.load(handle)
    if job.get("exit_code") != 0:
        raise SystemExit(f"{case_name}: happy-path job {capability_id} exited with {job.get('exit_code')!r}")

    parsed_status = normalized_status(job.get("parsed_status"))
    summary_status = normalized_status(summary.get("status"))
    app_status = normalized_status(summary.get("app_status"))
    legacy_env_ready = capability_id == "datanalysis_env.status" and summary.get("found") is True
    if parsed_status is None and not legacy_env_ready:
        raise SystemExit(f"{case_name}: missing parsed_status for {capability_id}")
    if summary_status is None and not legacy_env_ready:
        raise SystemExit(f"{case_name}: missing summary status for {capability_id}")
    if parsed_status is not None and summary_status is not None and parsed_status != summary_status:
        raise SystemExit(
            f"{case_name}: parsed_status/summary mismatch for {capability_id}: "
            f"{job.get('parsed_status')!r} vs {summary.get('status')!r}"
        )
    effective_status = summary_status or parsed_status or app_status
    if app_status is not None and effective_status is not None and app_status != effective_status:
        raise SystemExit(
            f"{case_name}: app_status/summary mismatch for {capability_id}: "
            f"{summary.get('app_status')!r} vs {summary.get('status')!r}"
        )
    if effective_status is not None and effective_status not in {"PASS", "WARNING"}:
        raise SystemExit(
            f"{case_name}: happy path rejected status for {capability_id}: "
            f"parsed={job.get('parsed_status')!r} app={summary.get('app_status')!r}"
        )
    original_modified = summary.get("original_modified")
    valid_original_modified = (
        original_modified is None
        or original_modified is False
        or (isinstance(original_modified, str) and original_modified.strip().lower() in {"false", "unknown"})
    )
    if not valid_original_modified:
        raise SystemExit(
            f"{case_name}: {capability_id} reported an invalid or true original_modified value: "
            f"{original_modified!r}"
        )

    manifest_optional = {
        "datanalysis_env.status",
        "coursework_notebook_fidelity_check",
        "physical_qa",
    }
    if capability_id not in manifest_optional:
        manifest_path = os.path.join(run_directory, "manifest.json")
        if not os.path.isfile(manifest_path):
            raise SystemExit(f"{case_name}: missing manifest.json for {capability_id}")

    artifacts = job.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise SystemExit(f"{case_name}: transcript does not list artifacts for {capability_id}")
    if job.get("artifact_count") != len(artifacts):
        raise SystemExit(f"{case_name}: artifact_count mismatch for {capability_id}")

summary_root = os.path.join(output_root, "Workflow Summaries")
if not os.path.isdir(summary_root):
    raise SystemExit(f"{case_name}: missing Workflow Summaries directory")

summary_files = sorted(
    os.path.join(summary_root, name)
    for name in os.listdir(summary_root)
    if name.endswith("_workflow_summary.md")
)
if not summary_files:
    raise SystemExit(f"{case_name}: missing workflow summary markdown")

with open(summary_files[-1], "r", encoding="utf-8") as handle:
    summary_text = handle.read()

expected_status_line = f"Status: Workflow finished: {len(expected)}/{len(expected)} enabled steps completed."
if expected_status_line not in summary_text:
    raise SystemExit(
        f"{case_name}: workflow did not finish every expected step; "
        f"missing status line {expected_status_line!r}"
    )

required_sections = [
    "# Scientific Workbench Workflow Summary",
    "## Read-Only Inputs",
    "## Enabled Steps",
    "## Jobs",
    "## Indexed Artifacts",
    "## PDF Deliverables",
    "## Safety Note",
    "Original input paths are not modified",
]
missing_sections = [section for section in required_sections if section not in summary_text]
if missing_sections:
    raise SystemExit(f"{case_name}: workflow summary missing sections {missing_sections}")

missing_summary_steps = [capability for capability in expected if capability not in summary_text]
if missing_summary_steps:
    raise SystemExit(f"{case_name}: workflow summary missing expected steps {missing_summary_steps}")

if expected and scoped_jobs:
    missing_summary_jobs = [job.get("capability_label") for job in scoped_jobs if job.get("capability_label") not in summary_text]
    if missing_summary_jobs:
        raise SystemExit(f"{case_name}: workflow summary missing job labels {missing_summary_jobs}")

print(f"ok {case_name}: executed {' '.join(job_ids)}")
PY
}

validate_blocked_stilts_app_case() {
  local transcript="$1"
  local case_name="$2"
  local output_root="$3"
  local app_exit_code="$4"
  /usr/bin/python3 - \
    "$transcript" \
    "$case_name" \
    "$output_root" \
    "$app_exit_code" <<'PY'
import json
import os
import sys

transcript_path, case_name, output_root, app_exit_code = sys.argv[1:5]
output_root = os.path.realpath(output_root)

def normalized_status(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip().upper()
    return {
        "OK": "PASS",
        "PASS": "PASS",
        "SUCCESS": "PASS",
        "SUCCEEDED": "PASS",
        "READY": "PASS",
        "WARNING": "WARNING",
        "WARN": "WARNING",
        "BLOCKED": "BLOCKED_CONTROLADO",
        "BLOCKED_CONTROLADO": "BLOCKED_CONTROLADO",
        "FAIL": "FAIL",
        "FAILED": "FAIL",
        "ERROR": "FAIL",
        "ROTO": "ROTO",
    }.get(normalized, normalized)

if int(app_exit_code) != 0:
    raise SystemExit(f"{case_name}: headless app process exited with {app_exit_code}")
if not os.path.isfile(transcript_path):
    raise SystemExit(f"{case_name}: missing launch transcript")

with open(transcript_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

plan = payload.get("agent_plan")
if not isinstance(plan, dict):
    raise SystemExit(f"{case_name}: missing structured agent_plan")
if plan.get("source") != "skillRouter":
    raise SystemExit(f"{case_name}: expected skillRouter plan, got {plan.get('source')!r}")

steps = plan.get("steps")
if not isinstance(steps, list):
    raise SystemExit(f"{case_name}: missing plan steps")
all_step_ids = [step.get("capability_id") for step in steps]
expected_plan = [
    "datanalysis_env.status",
    "stilts_workbench",
    "profile_table",
    "cross_domain_data_workbench",
]
if all_step_ids != expected_plan:
    raise SystemExit(f"{case_name}: STILTS plan changed; expected {expected_plan}, got {all_step_ids}")
enabled_ids = [step.get("capability_id") for step in steps if step.get("is_enabled", True)]
if enabled_ids != expected_plan:
    raise SystemExit(f"{case_name}: expected the full STILTS scenario to be enabled; got {enabled_ids}")

stilts_index = enabled_ids.index("stilts_workbench")
later_planned = enabled_ids[stilts_index + 1:]
if not later_planned:
    raise SystemExit(f"{case_name}: fixture needs a planned post-STILTS step to prove stop-on-block")
if not {"profile_table", "cross_domain_data_workbench"}.intersection(later_planned):
    raise SystemExit(f"{case_name}: expected a normal catalog follow-up after STILTS, got {later_planned}")

jobs = payload.get("jobs")
if not isinstance(jobs, list):
    raise SystemExit(f"{case_name}: missing jobs list")
scoped_jobs = []
for job in jobs:
    run_directory = job.get("run_directory")
    if not isinstance(run_directory, str):
        continue
    real_run = os.path.realpath(run_directory)
    if real_run == output_root or real_run.startswith(output_root + os.sep):
        scoped_jobs.append(job)

job_ids = [job.get("capability_id") for job in scoped_jobs]
expected_job_ids = {"datanalysis_env.status", "stilts_workbench"}
if len(scoped_jobs) != 2 or set(job_ids) != expected_job_ids:
    raise SystemExit(
        f"{case_name}: expected only environment and blocked STILTS jobs; got {job_ids}; "
        f"later planned={later_planned}"
    )
executed_later = [capability for capability in later_planned if capability in job_ids]
if executed_later:
    raise SystemExit(f"{case_name}: steps after blocked STILTS were executed: {executed_later}")

jobs_by_id = {job.get("capability_id"): job for job in scoped_jobs}
environment_job = jobs_by_id["datanalysis_env.status"]
stilts_job = jobs_by_id["stilts_workbench"]
if environment_job.get("status") != "succeeded" or environment_job.get("exit_code") != 0:
    raise SystemExit(f"{case_name}: environment job did not succeed: {environment_job!r}")
environment_status = normalized_status(environment_job.get("parsed_status"))
if environment_status not in {None, "PASS", "WARNING"}:
    raise SystemExit(
        f"{case_name}: unexpected environment parsed_status {environment_job.get('parsed_status')!r}"
    )

if stilts_job.get("status") != "blocked":
    raise SystemExit(f"{case_name}: STILTS job must be blocked, got {stilts_job.get('status')!r}")
if stilts_job.get("exit_code") != 2:
    raise SystemExit(f"{case_name}: STILTS job must preserve exit 2, got {stilts_job.get('exit_code')!r}")
if normalized_status(stilts_job.get("parsed_status")) != "BLOCKED_CONTROLADO":
    raise SystemExit(
        f"{case_name}: parser did not preserve blocked status: {stilts_job.get('parsed_status')!r}"
    )

run_directory = stilts_job.get("run_directory")
summary_path = os.path.join(run_directory, "summary.json")
if not os.path.isfile(summary_path):
    raise SystemExit(f"{case_name}: missing STILTS summary.json")
with open(summary_path, "r", encoding="utf-8") as handle:
    summary = json.load(handle)

summary_status = normalized_status(summary.get("status"))
app_status = normalized_status(summary.get("app_status"))
if summary_status != "BLOCKED_CONTROLADO" or app_status != "BLOCKED_CONTROLADO":
    raise SystemExit(
        f"{case_name}: expected summary BLOCKED_CONTROLADO, "
        f"got status={summary.get('status')!r} app_status={summary.get('app_status')!r}"
    )
if normalized_status(stilts_job.get("parsed_status")) != summary_status:
    raise SystemExit(f"{case_name}: transcript parsed_status and summary status disagree")
if summary.get("original_modified") is not False:
    raise SystemExit(
        f"{case_name}: blocked STILTS summary must report original_modified=false, "
        f"got {summary.get('original_modified')!r}"
    )

errors = summary.get("errors") or []
if not any(error.get("kind") == "missing_optional_backend" for error in errors if isinstance(error, dict)):
    raise SystemExit(f"{case_name}: missing errors.kind=missing_optional_backend")

results = summary.get("results") or {}
alternative = results.get("native_alternative") or {}
if alternative.get("capability_id") != "catalog_workbench.crossmatch-sky":
    raise SystemExit(f"{case_name}: missing native catalog alternative: {alternative!r}")

for name in ("stdout.txt", "stderr.txt"):
    log_path = os.path.join(run_directory, name)
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            if "Traceback (most recent call last)" in handle.read():
                raise SystemExit(f"{case_name}: raw traceback leaked in {log_path}")

workflow_summary_root = os.path.join(output_root, "Workflow Summaries")
if not os.path.isdir(workflow_summary_root):
    raise SystemExit(f"{case_name}: missing Workflow Summaries directory")
workflow_summaries = sorted(
    os.path.join(workflow_summary_root, name)
    for name in os.listdir(workflow_summary_root)
    if name.endswith("_workflow_summary.md")
)
if not workflow_summaries:
    raise SystemExit(f"{case_name}: missing blocked workflow summary markdown")
with open(workflow_summaries[-1], "r", encoding="utf-8") as handle:
    workflow_summary = handle.read()
expected_workflow_status = (
    "Status: Workflow stopped at stilts_workbench.py: Blocked. "
    "Completed 1/4 enabled steps."
)
if expected_workflow_status not in workflow_summary:
    raise SystemExit(
        f"{case_name}: global workflow status did not preserve the controlled block; "
        f"missing {expected_workflow_status!r}"
    )
for required_line in (
    "1. `datanalysis_env.status` - Succeeded",
    "2. `stilts_workbench` - Blocked",
    "3. `profile_table` - Not run",
    "4. `cross_domain_data_workbench` - Not run",
):
    if required_line not in workflow_summary:
        raise SystemExit(f"{case_name}: blocked workflow summary missing {required_line!r}")

print(
    f"ok {case_name}: app planned {later_planned}, stopped after STILTS exit 2, "
    "and preserved the native alternative"
)
PY
}

run_case() {
  local enable_restricted="0"
  if [[ "${1:-}" == "--enable-restricted" ]]; then
    enable_restricted="1"
    shift
  fi
  local case_name="$1"
  local prompt="$2"
  local expected_csv="$3"
  shift 3
  local output_root="$TMP_ROOT/output/$case_name"
  local transcript="$output_root/transcript.json"
  local fingerprint_before="$output_root/input_fingerprint_before.json"
  local fingerprint_after="$output_root/input_fingerprint_after.json"
  mkdir -p "$output_root"

  local command=(
    "$APP_BINARY"
    --agent-mode workflow
    --agent-local-planner
    --agent-auto-run
    --agent-output-root "$output_root"
    --agent-prompt "$prompt"
    --agent-transcript-json "$transcript"
    --agent-isolated-session
    --agent-exit-after-run
  )
  if [[ "$enable_restricted" == "1" ]]; then
    command+=(--agent-enable-restricted-steps)
  fi

  for input_path in "$@"; do
    command+=(--agent-input "$input_path")
  done

  if [[ "$#" -gt 0 ]]; then
    fingerprint_inputs "$fingerprint_before" "$@"
  fi
  "${command[@]}"
  validate_transcript "$transcript" "$case_name" "$output_root" "$expected_csv"
  if [[ "$#" -gt 0 ]]; then
    fingerprint_inputs "$fingerprint_after" "$@"
    validate_inputs_unchanged "$fingerprint_before" "$fingerprint_after" "$case_name"
  fi
}

run_blocked_stilts_app_case() {
  local case_name="stilts-backend-absent"
  local input_file="$1"
  local output_root="$TMP_ROOT/output/$case_name"
  local transcript="$output_root/transcript.json"
  local fingerprint_before="$output_root/input_fingerprint_before.json"
  local fingerprint_after="$output_root/input_fingerprint_after.json"
  local missing_stilts="$TMP_ROOT/missing-backends/stilts"
  mkdir -p "$output_root"

  if [[ -e "$missing_stilts" ]]; then
    echo "$case_name: deterministic missing STILTS path unexpectedly exists: $missing_stilts" >&2
    return 1
  fi
  fingerprint_inputs "$fingerprint_before" "$input_file"
  local command=(
    "$APP_BINARY"
    --agent-mode workflow
    --agent-local-planner
    --agent-auto-run
    --agent-enable-restricted-steps
    --agent-output-root "$output_root"
    --agent-prompt "Check the optional STILTS backend explicitly, then profile this catalog if the preflight succeeds. Stop cleanly and show the native alternative if STILTS is unavailable."
    --agent-input "$input_file"
    --agent-transcript-json "$transcript"
    --agent-isolated-session
    --agent-exit-after-run
  )

  set +e
  STILTS_COMMAND="$missing_stilts" "${command[@]}"
  local app_exit_code=$?
  set -e

  fingerprint_inputs "$fingerprint_after" "$input_file"
  validate_inputs_unchanged "$fingerprint_before" "$fingerprint_after" "$case_name"
  validate_blocked_stilts_app_case "$transcript" "$case_name" "$output_root" "$app_exit_code"
}

CSV_FILE="$TMP_ROOT/fixtures/csv/table.csv"
DOC_FILE="$TMP_ROOT/fixtures/documents/notes.md"
NOTEBOOK_FILE="$TMP_ROOT/fixtures/notebooks/analysis.ipynb"
FITS_FILE="$TMP_ROOT/fixtures/fits/synthetic_2x2.fits"
MIXED_CSV="$TMP_ROOT/fixtures/mixed/measurements.csv"
MIXED_DOC="$TMP_ROOT/fixtures/mixed/notes.md"
STILTS_INPUT="$TMP_ROOT/fixtures/stilts/catalog.csv"

write_fixture_file "$CSV_FILE" "time,flux,error
1,2.4,0.1
2,2.9,0.1
3,3.3,0.2
"
write_fixture_file "$DOC_FILE" "# Practice Notes

This synthetic document describes a short local scientific workflow.
It is intentionally tiny and does not reference DOCUS or UCM.
"
write_fixture_file "$NOTEBOOK_FILE" '{"cells":[{"cell_type":"markdown","metadata":{},"source":["# Notebook smoke\n"]},{"cell_type":"code","execution_count":null,"metadata":{},"outputs":[],"source":["x = 1\n"]}],"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"}},"nbformat":4,"nbformat_minor":5}
'
write_valid_fits_fixture "$FITS_FILE"
write_fixture_file "$MIXED_CSV" "wavelength,flux
6707.1,0.82
6707.8,0.64
6708.4,0.91
"
write_fixture_file "$MIXED_DOC" "# Mixed Bundle

Synthetic notes paired with a small CSV table for cross-domain routing.
"
write_fixture_file "$STILTS_INPUT" "source_id,ra,dec
1,120.0000,-30.0000
2,120.0005,-30.0003
"

run_case \
  "readiness" \
  "Check Scientific Workbench readiness without inputs." \
  "datanalysis_env.status,datanalysis_healthcheck,env_doctor"

run_case \
  "csv-profile" \
  "Analyze this CSV table file safely and summarize the useful columns." \
  "datanalysis_env.status,profile_table,cross_domain_data_workbench" \
  "$CSV_FILE"

run_case \
  "document-intake" \
  "Analyze this document safely without editing the original." \
  "datanalysis_env.status,document_intake_workbench" \
  "$DOC_FILE"

run_case \
  --enable-restricted \
  "notebook-copy" \
  "Inspect and execute a safe copy of this notebook without editing the original." \
  "datanalysis_env.status,coursework_notebook_fidelity_check,notebook_workbench.execute-copy" \
  "$NOTEBOOK_FILE"

run_case \
  --enable-restricted \
  "fits-inspection-qa" \
  "Inspect this valid FITS image and run physical QA safely without modifying the original." \
  "datanalysis_env.status,inspect_fits,physical_qa" \
  "$FITS_FILE"

run_case \
  "mixed-csv-document" \
  "Analyze this mixed CSV and document bundle safely, then produce a first-pass inventory." \
  "datanalysis_env.status,profile_table,cross_domain_data_workbench,document_intake_workbench" \
  "$MIXED_CSV" \
  "$MIXED_DOC"

run_blocked_stilts_app_case "$STILTS_INPUT"

echo "Scientific Workbench E2E capability matrix passed."
