#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_ROOT="${MIXED_BENCHMARK_OUTPUT_ROOT:-$HOME/Documents/Scientific Workbench Runs/Mixed Benchmarks/$TIMESTAMP}"
FIXTURE_ROOT="$OUTPUT_ROOT/input/mixed_research_bundle"
RUN_OUTPUT="$OUTPUT_ROOT/run_output"
TRANSCRIPT="$RUN_OUTPUT/transcript.json"
FINGERPRINT_BEFORE="$OUTPUT_ROOT/input_fingerprint_before.json"
FINGERPRINT_AFTER="$OUTPUT_ROOT/input_fingerprint_after.json"
REPORT="$OUTPUT_ROOT/benchmark_report.md"
PROMPT="${MIXED_BENCHMARK_PROMPT:-Analyze this mixed local research bundle safely and produce a first-pass inventory without editing originals.}"

cd "$ROOT_DIR"
swift build >/dev/null
APP_BINARY="$(swift build --show-bin-path)/ScientificWorkbench"

mkdir -p "$FIXTURE_ROOT/tables" "$FIXTURE_ROOT/fits" "$FIXTURE_ROOT/docs" "$RUN_OUTPUT"

cat >"$FIXTURE_ROOT/README.md" <<'EOF'
# Mixed Research Bundle

Synthetic benchmark bundle for Scientific Workbench.

It contains a small observation table, a minimal FITS header-only file, notes,
and a tiny PDF. It intentionally does not use the UCM/DOCUS folder shape.
EOF

cat >"$FIXTURE_ROOT/tables/measurements.csv" <<'EOF'
wavelength_nm,flux,error
670.70,0.82,0.03
670.78,0.64,0.04
670.84,0.91,0.03
EOF

cat >"$FIXTURE_ROOT/docs/observing_notes.md" <<'EOF'
# Observing Notes

Target: synthetic lithium line check.
Goal: verify that the app routes a general mixed research folder through FITS,
table, document, and cross-domain capabilities without relying on DOCUS logic.
EOF

/usr/bin/python3 - "$FIXTURE_ROOT/fits/synthetic_header.fits" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
cards = [
    "SIMPLE  =                    T",
    "BITPIX  =                    8",
    "NAXIS   =                    0",
    "EXTEND  =                    T",
    "OBJECT  = 'Synthetic Target'",
    "DATE-OBS= '2026-05-31'",
    "TELESCOP= 'Scientific Workbench'",
    "END",
]
header = "".join(card.ljust(80) for card in cards).encode("ascii")
header += b" " * ((2880 - (len(header) % 2880)) % 2880)
path.write_bytes(header)
PY

cat >"$FIXTURE_ROOT/docs/tiny_reference.pdf" <<'EOF'
%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Count 0 >>
endobj
trailer
<< /Root 1 0 R >>
%%EOF
EOF

fingerprint_tree() {
  local output_file="$1"
  local input_path="$2"
  /usr/bin/python3 - "$output_file" "$input_path" <<'PY'
import hashlib
import json
import os
import sys

output_file, input_path = sys.argv[1:3]
records = []

def digest_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def add_record(path):
    real_path = os.path.realpath(path)
    if os.path.isdir(path):
        records.append({"path": real_path, "kind": "directory"})
    elif os.path.isfile(path):
        stat_result = os.stat(path)
        records.append({
            "path": real_path,
            "kind": "file",
            "size": stat_result.st_size,
            "sha256": digest_file(path),
        })
    else:
        records.append({"path": real_path, "kind": "other"})

add_record(input_path)
for directory, dirnames, filenames in os.walk(input_path, followlinks=False):
    dirnames[:] = sorted(dirnames)
    for dirname in dirnames:
        add_record(os.path.join(directory, dirname))
    for filename in sorted(filenames):
        add_record(os.path.join(directory, filename))

records.sort(key=lambda item: (item["path"], item["kind"]))
with open(output_file, "w", encoding="utf-8") as handle:
    json.dump(records, handle, indent=2, sort_keys=True)
PY
}

validate_inputs_unchanged() {
  /usr/bin/python3 - "$FINGERPRINT_BEFORE" "$FINGERPRINT_AFTER" <<'PY'
import json
import sys

before_path, after_path = sys.argv[1:3]
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
        f"Mixed benchmark input changed; added={added[:5]} removed={removed[:5]} changed={changed[:5]}"
    )
PY
}

validate_transcript_and_write_report() {
  /usr/bin/python3 - "$TRANSCRIPT" "$FIXTURE_ROOT" "$RUN_OUTPUT" "$REPORT" <<'PY'
import json
import os
import sys

transcript_path, fixture_root, run_output, report_path = sys.argv[1:5]
expected_steps = [
    "datanalysis_env.status",
    "document_intake_workbench",
    "cross_domain_data_workbench",
]
forbidden_steps = [
    "legacy_spectroscopy_envcheck",
    "fxcor_iraf_workbench.prepare-session",
    "fxcor_iraf_workbench.run-auto",
    "legacy_spectroscopy_report_builder.scaffold",
]

with open(transcript_path, "r", encoding="utf-8") as handle:
    payload = json.load(handle)

plan = payload.get("agent_plan")
if not isinstance(plan, dict):
    raise SystemExit("Mixed benchmark transcript is missing agent_plan")
if plan.get("source") not in {"local", "skillRouter"}:
    raise SystemExit(f"Mixed benchmark expected local or skillRouter planner, got {plan.get('source')!r}")

steps = plan.get("steps")
if not isinstance(steps, list):
    raise SystemExit("Mixed benchmark transcript is missing plan steps")
step_ids = [step.get("capability_id") for step in steps if step.get("is_enabled", True)]
missing = [step for step in expected_steps if step not in step_ids]
if missing:
    raise SystemExit(f"Mixed benchmark missing expected steps {missing}; got {step_ids}")
unexpected = [step for step in forbidden_steps if step in step_ids]
if unexpected:
    raise SystemExit(f"Mixed benchmark incorrectly used DOCUS/UCM legacy steps: {unexpected}")

jobs = payload.get("jobs") or []
run_real = os.path.realpath(run_output)
scoped_jobs = []
for job in jobs:
    run_directory = job.get("run_directory")
    if not isinstance(run_directory, str):
        continue
    real_run = os.path.realpath(run_directory)
    if real_run == run_real or real_run.startswith(run_real + os.sep):
        scoped_jobs.append(job)

job_ids = [job.get("capability_id") for job in scoped_jobs]
missing_jobs = [step for step in expected_steps if step not in job_ids]
if missing_jobs:
    raise SystemExit(f"Mixed benchmark missing executed jobs {missing_jobs}; got {job_ids}")
bad_jobs = [job for job in scoped_jobs if job.get("status") != "succeeded"]
if bad_jobs:
    details = [f"{job.get('capability_id')}={job.get('status')} exit={job.get('exit_code')}" for job in bad_jobs]
    raise SystemExit(f"Mixed benchmark expected all jobs to succeed; {details}")

artifact_count = 0
for job in scoped_jobs:
    artifacts = job.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise SystemExit(f"Mixed benchmark job has no artifacts: {job.get('capability_id')}")
    artifact_count += len(artifacts)
    summary_path = os.path.join(job.get("run_directory"), "summary.json")
    if not os.path.isfile(summary_path):
        raise SystemExit(f"Mixed benchmark missing summary.json for {job.get('capability_id')}")
    with open(summary_path, "r", encoding="utf-8") as handle:
        summary = json.load(handle)
    status = summary.get("status")
    if job.get("capability_id") == "datanalysis_env.status" and summary.get("found") is True:
        continue
    if status not in {"ok", "warning", "success", "succeeded"}:
        raise SystemExit(f"Mixed benchmark unexpected summary status for {job.get('capability_id')}: {status!r}")

summary_root = os.path.join(run_output, "Workflow Summaries")
summaries = []
if os.path.isdir(summary_root):
    summaries = sorted(name for name in os.listdir(summary_root) if name.endswith("_workflow_summary.md"))
if not summaries:
    raise SystemExit("Mixed benchmark did not produce a workflow summary")

report = [
    "# Mixed Research Benchmark Report",
    "",
    f"- Input fixture: `{fixture_root}`",
    f"- Run output: `{run_output}`",
    f"- Transcript: `{transcript_path}`",
    f"- Planned enabled steps: `{len(step_ids)}`",
    f"- Executed jobs: `{len(scoped_jobs)}`",
    f"- Artifact count: `{artifact_count}`",
    "",
    "## Plan",
    "",
]
report.extend(f"{index}. `{step}`" for index, step in enumerate(step_ids, start=1))
report.extend(["", "## Jobs", ""])
report.extend(f"- `{job.get('capability_id')}`: {job.get('status')}, exit {job.get('exit_code')}" for job in scoped_jobs)
report.extend([
    "",
    "## Safety Checks",
    "",
    "- The mixed benchmark fixture was fingerprinted before and after execution.",
    "- The workflow used general mixed-data routing, not DOCUS/UCM legacy routing.",
])

with open(report_path, "w", encoding="utf-8") as handle:
    handle.write("\n".join(report) + "\n")

print(f"ok mixed research benchmark: {len(step_ids)} planned steps, {len(scoped_jobs)} jobs, {artifact_count} artifacts")
PY
}

fingerprint_tree "$FINGERPRINT_BEFORE" "$FIXTURE_ROOT"

"$APP_BINARY" \
  --agent-mode workflow \
  --agent-local-planner \
  --agent-auto-run \
  --agent-output-root "$RUN_OUTPUT" \
  --agent-prompt "$PROMPT" \
  --agent-input "$FIXTURE_ROOT" \
  --agent-transcript-json "$TRANSCRIPT" \
  --agent-isolated-session \
  --agent-exit-after-run

fingerprint_tree "$FINGERPRINT_AFTER" "$FIXTURE_ROOT"
validate_inputs_unchanged
validate_transcript_and_write_report

echo "Scientific Workbench mixed research benchmark passed."
echo "Benchmark report: $REPORT"
